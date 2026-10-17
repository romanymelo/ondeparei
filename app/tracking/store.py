"""Onde ficam as marcações de uma pessoa: a interface comum e o "store" de quem não está logado."""

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Protocol

from app.auth.client import User
from app.auth.session import LoginRequired
from app.models import Marks, TrackedSeries

Ep = tuple[int, int]

logger = logging.getLogger(__name__)


class TrackingUnavailable(Exception):
    """O banco das marcações (Supabase) não respondeu ou recusou a sessão."""


class TrackingStore(Protocol):
    async def marks(self, tmdb_id: int) -> Marks: ...

    async def marks_for(self, tmdb_ids: Sequence[int]) -> dict[int, Marks]: ...

    async def watched(self, tmdb_id: int) -> frozenset[Ep]: ...

    async def save(self, tmdb_id: int, *, name: str, poster_path: str | None, status: str | None, favorite: bool,
                   add: Iterable[Ep] = (), remove: Iterable[Ep] = (),
                   runtimes: Mapping[Ep, int | None] = {}) -> None: ...

    async def counts(self) -> dict[str, int]: ...

    async def list_tab(self, tab: str) -> list[TrackedSeries]: ...

    async def watch_time(self) -> tuple[int, int]: ...

    async def missing_runtimes(self) -> dict[int, set[int]]: ...

    async def set_runtimes(self, tmdb_id: int, runtimes: Mapping[Ep, int]) -> None: ...


StoreFactory = Callable[[User, str], TrackingStore]


class VisitorStore:
    """Quem não está logado: nada marcado; qualquer gravação pede login."""

    async def marks(self, tmdb_id: int) -> Marks:
        return Marks()

    async def marks_for(self, tmdb_ids: Sequence[int]) -> dict[int, Marks]:
        return {}

    async def watched(self, tmdb_id: int) -> frozenset[Ep]:
        return frozenset()

    async def save(self, tmdb_id: int, **kw) -> None:
        raise LoginRequired()

    async def counts(self) -> dict[str, int]:
        return {"watching": 0, "want": 0, "watched": 0, "favorite": 0}

    async def list_tab(self, tab: str) -> list[TrackedSeries]:
        return []

    async def watch_time(self) -> tuple[int, int]:
        return 0, 0

    async def missing_runtimes(self) -> dict[int, set[int]]:
        return {}

    async def set_runtimes(self, tmdb_id: int, runtimes: Mapping[Ep, int]) -> None:
        raise LoginRequired()


class ReadSafeStore:
    """Envolve o store de quem está logado nas páginas abertas a todos: leituras que falham viram "nada
    marcado" (com aviso no log); gravações seguem normais e mostram o erro."""

    def __init__(self, inner: TrackingStore) -> None:
        self._inner = inner
        self._visitor = VisitorStore()

    def __getattr__(self, name):
        target = getattr(self._inner, name)
        if name in ("save", "set_runtimes"):
            return target

        async def safe(*args, **kwargs):
            try:
                return await target(*args, **kwargs)
            except TrackingUnavailable as exc:
                logger.warning("Marcações indisponíveis (%s): página aberta sem elas", exc)
                return await getattr(self._visitor, name)(*args, **kwargs)
        return safe
