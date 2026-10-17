import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from app.tmdb.cache import TTLCache, make_key

BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_RETRY_AFTER = 1.0
MAX_RETRY_AFTER = 2.0

logger = logging.getLogger(__name__)


class TMDBError(Exception):
    pass


class TMDBAuthError(TMDBError):
    pass


class TMDBNotFound(TMDBError):
    pass


class TMDBUnavailable(TMDBError):
    pass


def create_http_client(token: str, timeout: float = 10.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=timeout,
    )


def _retry_after_seconds(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", DEFAULT_RETRY_AFTER))
    except ValueError:
        seconds = DEFAULT_RETRY_AFTER
    return min(seconds, MAX_RETRY_AFTER)


class TMDBClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        cache: TTLCache,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._cache = cache
        self._sleep = sleep

    async def get(self, path: str, params: Mapping[str, Any] | None = None, *, ttl: float) -> dict[str, Any]:
        params = dict(params or {})
        key = make_key(path, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        response = await self._request(path, params)
        if response.status_code == 429:
            await self._sleep(_retry_after_seconds(response))
            response = await self._request(path, params)

        if response.is_success:
            data = response.json()
            self._cache.set(key, data, ttl)
            return data

        logger.warning("TMDB respondeu %s em %s", response.status_code, path)
        if response.status_code == 401:
            raise TMDBAuthError(f"401 em {path}")
        if response.status_code == 404:
            raise TMDBNotFound(f"404 em {path}")
        raise TMDBUnavailable(f"{response.status_code} em {path}")

    async def _request(self, path: str, params: dict[str, Any]) -> httpx.Response:
        try:
            return await self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede ao chamar a TMDB em %s: %s", path, type(exc).__name__)
            raise TMDBUnavailable(f"falha de rede em {path}") from exc
