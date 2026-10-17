"""Marcações no banco do Supabase (PostgREST), sempre com o token da própria pessoa: a RLS faz a separação."""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import httpx

from app.mappers import image_url
from app.models import Marks, TrackedSeries
from app.tracking.service import InvalidAction
from app.tracking.store import TrackingUnavailable

Ep = tuple[int, int]
READ_PAGE = 1000  # máximo de linhas por resposta do PostgREST

_TAB_FILTERS = {
    "watching": ("status", "eq.watching"),
    "want": ("status", "eq.want"),
    "watched": ("status", "eq.watched"),
    "favorite": ("favorite", "is.true"),
}


class SupabaseTrackingRepository:
    def __init__(self, http: httpx.AsyncClient, url: str, publishable_key: str, access_token: str) -> None:
        self._http = http
        self._base = f"{url.rstrip('/')}/rest/v1"
        self._headers = {"apikey": publishable_key, "Authorization": f"Bearer {access_token}"}

    async def _request(self, method: str, path: str, *, params: dict | None = None, json: Any = None,
                       invalid_is_action: bool = False) -> Any:
        try:
            response = await self._http.request(method, f"{self._base}{path}", params=params, json=json,
                                                headers=self._headers)
        except httpx.HTTPError as exc:
            raise TrackingUnavailable(str(exc)) from exc
        if response.status_code >= 500 or response.status_code in (401, 403, 404):
            # 403/404: SQL ainda não aplicado ou grant faltando; não é erro de quem clicou
            raise TrackingUnavailable(f"{response.status_code} {response.text[:200]}")
        if response.status_code >= 400:
            if invalid_is_action:
                raise InvalidAction(response.text[:200])
            raise TrackingUnavailable(f"{response.status_code} {response.text[:200]}")
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise TrackingUnavailable("resposta não é JSON") from exc

    async def _rpc(self, name: str, body: dict | None = None, **kw) -> Any:
        return await self._request("POST", f"/rpc/{name}", json=body or {}, **kw)

    async def marks(self, tmdb_id: int) -> Marks:
        return (await self.marks_for([tmdb_id])).get(tmdb_id, Marks())

    async def marks_for(self, tmdb_ids: Sequence[int]) -> dict[int, Marks]:
        if not tmdb_ids:
            return {}
        rows = await self._request("GET", "/series_tracking", params={
            "select": "tmdb_id,status,favorite", "tmdb_id": f"in.({','.join(str(i) for i in tmdb_ids)})"})
        return {row["tmdb_id"]: Marks(row["status"], bool(row["favorite"])) for row in rows or []}

    async def watched(self, tmdb_id: int) -> frozenset[Ep]:
        episodes: set[Ep] = set()
        offset = 0
        while True:  # em páginas: séries longas passam de 1000 episódios
            rows = await self._request("GET", "/watched_episodes", params={
                "select": "season,episode", "tmdb_id": f"eq.{tmdb_id}", "order": "season,episode",
                "limit": str(READ_PAGE), "offset": str(offset)}) or []
            episodes.update((row["season"], row["episode"]) for row in rows)
            if len(rows) < READ_PAGE:
                return frozenset(episodes)
            offset += READ_PAGE

    async def save(self, tmdb_id: int, *, name: str, poster_path: str | None, status: str | None, favorite: bool,
                   add: Iterable[Ep] = (), remove: Iterable[Ep] = (),
                   runtimes: Mapping[Ep, int | None] = {}) -> None:
        await self._rpc("save_tracking", {
            "p_tmdb_id": tmdb_id, "p_name": name, "p_poster_path": poster_path, "p_status": status,
            "p_favorite": favorite,
            "p_add": [{"season": s, "episode": e, "runtime": runtimes.get((s, e))} for s, e in add],
            "p_remove": [{"season": s, "episode": e} for s, e in remove],
        }, invalid_is_action=True)

    async def counts(self) -> dict[str, int]:
        data = await self._rpc("tracking_counts") or {}
        return {key: int(data.get(key) or 0) for key in ("watching", "want", "watched", "favorite")}

    async def list_tab(self, tab: str) -> list[TrackedSeries]:
        column, value = _TAB_FILTERS[tab]
        rows = await self._request("GET", "/series_tracking", params={
            "select": "tmdb_id,name,poster_path,status,favorite", column: value, "order": "updated_at.desc"})
        return [TrackedSeries(row["tmdb_id"], row["name"], image_url(row["poster_path"], "w342"),
                              Marks(row["status"], bool(row["favorite"]))) for row in rows or []]

    async def watch_time(self) -> tuple[int, int]:
        data = await self._rpc("watch_time") or {}
        return int(data.get("episodes") or 0), int(data.get("minutes") or 0)

    async def missing_runtimes(self) -> dict[int, set[int]]:
        missing: dict[int, set[int]] = {}
        for row in await self._rpc("missing_runtimes") or []:
            missing.setdefault(row["tmdb_id"], set()).add(row["season"])
        return missing

    async def set_runtimes(self, tmdb_id: int, runtimes: Mapping[Ep, int]) -> None:
        await self._rpc("set_runtimes", {
            "p_tmdb_id": tmdb_id,
            "p_runtimes": [{"season": s, "episode": e, "runtime": minutes} for (s, e), minutes in runtimes.items()],
        })
