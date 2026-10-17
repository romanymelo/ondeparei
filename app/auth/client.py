"""Cliente do serviço de login do Supabase ({SUPABASE_URL}/auth/v1), só com httpx."""

import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class User:
    id: str
    email: str
    first_name: str
    last_name: str


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    expires_at: int  # epoch em segundos
    user: User


class AuthError(Exception):
    """Falha numa operação de conta."""


class InvalidCredentials(AuthError):
    pass


class EmailTaken(AuthError):
    pass


class WeakPassword(AuthError):
    pass


class RateLimited(AuthError):
    pass


class AuthUnavailable(AuthError):
    """Supabase fora do ar, com erro interno ou resposta que não é JSON."""


class InvalidRecoveryLink(AuthError):
    pass


class InvalidSession(AuthError):
    """Token de acesso ou de renovação recusado: a pessoa precisa entrar de novo."""


_BY_CODE = {
    "invalid_credentials": InvalidCredentials,
    "user_already_exists": EmailTaken,
    "email_exists": EmailTaken,
    "weak_password": WeakPassword,
    "otp_expired": InvalidRecoveryLink,
    "refresh_token_not_found": InvalidSession,
}


def _user(data: dict[str, Any]) -> User:
    meta = data.get("user_metadata") or {}
    return User(data["id"], data.get("email") or "", meta.get("first_name") or "", meta.get("last_name") or "")


def _session(data: dict[str, Any]) -> Session:
    expires_at = data.get("expires_at") or int(time.time()) + int(data.get("expires_in") or 0)
    return Session(data["access_token"], data["refresh_token"], int(expires_at), _user(data["user"]))


class SupabaseAuth:
    def __init__(self, http: httpx.AsyncClient, url: str, publishable_key: str) -> None:
        self._http = http
        self._base = f"{url.rstrip('/')}/auth/v1"
        self._key = publishable_key

    async def _call(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None,
                    token: str | None = None, session_call: bool = False) -> Any:
        """Faz a chamada e traduz os erros. `session_call`: 400/401/403 querem dizer sessão inválida."""
        headers = {"apikey": self._key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = await self._http.request(method, f"{self._base}{path}", json=json, params=params,
                                                headers=headers)
        except httpx.HTTPError as exc:
            raise AuthUnavailable(str(exc)) from exc
        if response.status_code == 204:
            return None
        try:
            data = response.json()
        except ValueError as exc:
            raise AuthUnavailable(f"resposta não é JSON ({response.status_code})") from exc
        if response.is_success:
            return data
        code = (data or {}).get("error_code") if isinstance(data, dict) else None
        if response.status_code == 429:
            raise RateLimited(code or "429")
        if response.status_code >= 500:
            raise AuthUnavailable(f"{response.status_code} {code or ''}")
        if session_call and response.status_code in (400, 401, 403):
            raise InvalidSession(code or str(response.status_code))
        raise _BY_CODE.get(code, AuthError)(code or str(response.status_code))

    async def sign_up(self, email: str, password: str, first_name: str, last_name: str) -> Session:
        data = await self._call("POST", "/signup", json={
            "email": email, "password": password, "data": {"first_name": first_name, "last_name": last_name}})
        return _session(data)

    async def sign_in(self, email: str, password: str) -> Session:
        data = await self._call("POST", "/token", params={"grant_type": "password"},
                                json={"email": email, "password": password})
        return _session(data)

    async def refresh(self, refresh_token: str) -> Session:
        data = await self._call("POST", "/token", params={"grant_type": "refresh_token"},
                                json={"refresh_token": refresh_token}, session_call=True)
        return _session(data)

    async def get_user(self, access_token: str) -> User:
        return _user(await self._call("GET", "/user", token=access_token, session_call=True))

    async def sign_out(self, access_token: str) -> None:
        # scope=local: sai só deste navegador, sem derrubar a sessão em outros aparelhos
        await self._call("POST", "/logout", params={"scope": "local"}, token=access_token, session_call=True)

    async def recover(self, email: str) -> None:
        await self._call("POST", "/recover", json={"email": email})

    async def verify_recovery(self, token_hash: str) -> Session:
        try:
            data = await self._call("POST", "/verify", json={"type": "recovery", "token_hash": token_hash})
        except (AuthUnavailable, RateLimited):
            raise
        except AuthError as exc:  # link vencido, já usado ou adulterado
            raise InvalidRecoveryLink(str(exc)) from exc
        return _session(data)

    async def update_password(self, access_token: str, password: str) -> None:
        await self._call("PUT", "/user", json={"password": password}, token=access_token, session_call=True)
