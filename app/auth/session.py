"""Sessão em cookies: quem é a pessoa em cada pedido, com cache curto e renovação automática do token."""

import base64
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.client import AuthUnavailable, InvalidSession, Session, User
from app.auth.forms import safe_next
from app.templating import is_htmx
from app.tmdb.cache import TTLCache

ACCESS_COOKIE = "op_acesso"
REFRESH_COOKIE = "op_renovacao"
REFRESH_MAX_AGE = 180 * 24 * 3600
USER_CACHE_TTL = 300


class LoginRequired(Exception):
    """Ação que precisa de conta, feita por um visitante."""


@dataclass
class Resolution:
    user: User | None
    access_token: str | None
    new_session: Session | None = None
    clear: bool = False


def set_session_cookies(response: Response, session: Session, secure: bool) -> None:
    common = {"httponly": True, "samesite": "lax", "path": "/", "secure": secure}
    response.set_cookie(ACCESS_COOKIE, session.access_token, max_age=REFRESH_MAX_AGE, **common)
    response.set_cookie(REFRESH_COOKIE, session.refresh_token, max_age=REFRESH_MAX_AGE, **common)


def clear_session_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", httponly=True, samesite="lax")


def _token_expiry(token: str) -> int | None:
    """O "exp" do JWT, só para não guardar no cache além do vencimento (quem valida é o Supabase)."""
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return int(data["exp"])
    except (IndexError, ValueError, KeyError, TypeError):
        return None


class UserResolver:
    def __init__(self, auth, clock: Callable[[], float] = time.time) -> None:
        self._auth = auth
        self._clock = clock
        self._cache = TTLCache(clock=clock)

    async def resolve(self, access: str | None, refresh: str | None) -> Resolution:
        if access:
            key = hashlib.sha256(access.encode()).hexdigest()
            cached = self._cache.get(key)
            if cached is not None:
                return Resolution(cached, access)
            try:
                user = await self._auth.get_user(access)
            except AuthUnavailable:
                return Resolution(None, None)
            except InvalidSession:
                user = None
            if user is not None:
                expiry = _token_expiry(access)
                ttl = USER_CACHE_TTL if expiry is None else min(USER_CACHE_TTL, expiry - self._clock())
                if ttl > 0:
                    self._cache.set(key, user, ttl)
                return Resolution(user, access)
        if not refresh:
            return Resolution(None, None, clear=bool(access))
        try:
            session = await self._auth.refresh(refresh)
        except AuthUnavailable:
            return Resolution(None, None)
        except InvalidSession:
            return Resolution(None, None, clear=True)
        return Resolution(session.user, session.access_token, new_session=session)


class SessionMiddleware(BaseHTTPMiddleware):
    """Preenche request.state.user e access_token; regrava ou apaga os cookies na resposta."""

    async def dispatch(self, request: Request, call_next):
        resolver: UserResolver | None = getattr(request.app.state, "resolver", None)
        resolution = Resolution(None, None)
        if resolver is not None:
            resolution = await resolver.resolve(request.cookies.get(ACCESS_COOKIE),
                                                request.cookies.get(REFRESH_COOKIE))
        request.state.user = resolution.user
        request.state.access_token = resolution.access_token
        request.state.watch_time = None
        response = await call_next(request)
        if resolution.new_session is not None:
            set_session_cookies(response, resolution.new_session, secure=request.url.scheme == "https")
        elif resolution.clear:
            clear_session_cookies(response)
        return response


def _relative(url: str | None) -> str:
    if not url:
        return "/"
    parts = urlsplit(url)
    return safe_next(f"{parts.path}?{parts.query}" if parts.query else parts.path)


def login_redirect(request: Request) -> Response:
    """Leva o visitante para Entrar, lembrando de onde ele veio."""
    if is_htmx(request):
        target = _relative(request.headers.get("HX-Current-URL"))
    elif request.method == "GET":
        target = _relative(str(request.url))
    else:
        target = _relative(request.headers.get("referer"))
    location = f"/entrar?proximo={quote(target, safe='')}"
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": location})
    return RedirectResponse(location, status_code=303)
