"""CSRF: pedidos que mudam algo só valem quando vêm do próprio site (Origin, ou Referer na falta dele)."""

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE_METHODS:
            own = f"{request.url.scheme}://{request.url.netloc}"
            origin = request.headers.get("origin")
            if origin is None:
                referer = request.headers.get("referer")
                origin = _origin_of(referer) if referer else None
            if origin != own:
                return HTMLResponse("<p>Pedido recusado</p>", status_code=403)
        return await call_next(request)
