"""TrackingService: busca a TMDB (pelo Catalog), valida, aplica as regras e grava numa transação."""

import asyncio
import dataclasses
from collections.abc import Callable, Collection, Sequence
from datetime import date

from app.models import Marks, MySeries, SeasonDetail, SeasonView, SeriesDetail, SeriesTracking, TrackedSeries
from app.tmdb.client import TMDBError
from app.tracking.repository import TrackingRepository
from app.tracking.rules import (Ep, aired_episodes, aired_specials, auto_status, next_episode, progress,
                                season_episodes, up_to)

STATUSES = ("want", "watching", "watched")
TABS = {"assistindo": "watching", "quero": "want", "assistidas": "watched", "favoritas": "favorite"}
DEFAULT_TAB = "assistindo"
DETAIL_CONCURRENCY = 10

# Escolhe o que marcar e desmarcar: (exibidos da temporada, exibidos da série, já marcados) -> (add, remove)
Choice = Callable[[list[Ep], list[Ep], frozenset[Ep]], tuple[set[Ep], set[Ep]]]


class InvalidAction(ValueError):
    """Entrada inválida numa ação: status desconhecido, episódio inexistente ou que ainda não foi ao ar."""


def _runtimes(season: SeasonDetail, typical: int | None) -> dict[Ep, int | None]:
    """Duração de cada episódio da temporada; sem ela na TMDB, a típica da série."""
    return {(season.number, e.number): e.runtime or typical for e in season.episodes}


def _aired(detail: SeriesDetail) -> list[Ep]:
    return aired_episodes(((s.number, s.episode_count) for s in detail.seasons), detail.last_aired)


class TrackingService:
    def __init__(self, catalog, repo: TrackingRepository, today: Callable[[], date] = date.today) -> None:
        self._catalog = catalog
        self._repo = repo
        self._today = today

    def marks_for(self, tmdb_ids: Sequence[int]) -> dict[int, Marks]:
        return self._repo.marks_for(tmdb_ids)

    # Página da série: status, favorito e progresso das temporadas
    async def series(self, detail: SeriesDetail) -> SeriesTracking:
        return await self._tracking(detail.id, detail)

    async def set_status(self, series_id: int, status: str) -> SeriesTracking:
        if status not in STATUSES:
            raise InvalidAction(f"status {status!r}")
        detail = await self._catalog.detail(series_id)
        marks = self._repo.marks(series_id)
        new_status = None if marks.status == status else status
        # o status combina com os episódios: "Assistido" marca todos os já exibidos (Especiais ficam de fora);
        # sair de "Assistido" desmarca tudo, inclusive Especiais
        add = _aired(detail) if new_status == "watched" else ()
        remove = self._repo.watched(series_id) if marks.status == "watched" else ()
        self._save(series_id, detail, new_status, marks.favorite, add=add, remove=remove)
        return await self._tracking(series_id, detail)

    async def toggle_favorite(self, series_id: int) -> SeriesTracking:
        detail = await self._catalog.detail(series_id)
        marks = self._repo.marks(series_id)
        self._save(series_id, detail, marks.status, not marks.favorite)
        return await self._tracking(series_id, detail)

    async def _tracking(self, series_id: int, detail: SeriesDetail) -> SeriesTracking:
        marks = self._repo.marks(series_id)
        watched = self._repo.watched(series_id)
        aired = _aired(detail)
        upcoming = next_episode(aired, watched)
        title = None
        if marks.status == "watching" and upcoming:
            try:
                season = await self._catalog.season(series_id, upcoming[0])
                title = next((e.name for e in season.episodes if e.number == upcoming[1]), None)
            except TMDBError:
                pass
        season_progress = {
            s.number: (sum(1 for ep in watched if ep[0] == 0), 0) if s.number == 0
            else progress(season_episodes(aired, s.number), watched)
            for s in detail.seasons
        }
        return SeriesTracking(marks, upcoming, title, season_progress)

    # Página da temporada e ações nos episódios
    async def season(self, series_id: int, number: int) -> SeasonView:
        detail, season = await asyncio.gather(self._catalog.detail(series_id), self._catalog.season(series_id, number))
        return self._view(series_id, detail, season)

    async def toggle_episode(self, series_id: int, season: int, episode: int) -> SeasonView:
        target = (season, episode)

        def choose(aired_season, aired, watched):
            if target not in aired_season:
                raise InvalidAction(f"episódio {target} não exibido")
            return (set(), {target}) if target in watched else ({target}, set())

        return await self._episode_action(series_id, season, choose)

    async def mark_up_to(self, series_id: int, season: int, episode: int) -> SeasonView:
        target = (season, episode)

        def choose(aired_season, aired, watched):
            if target not in aired_season:
                raise InvalidAction(f"episódio {target} não exibido")
            if season == 0:
                return {ep for ep in aired_season if ep <= target}, set()
            return set(up_to(aired, target)), set()

        return await self._episode_action(series_id, season, choose)

    async def toggle_season(self, series_id: int, season: int) -> SeasonView:
        def choose(aired_season, aired, watched):
            if not aired_season:
                raise InvalidAction(f"temporada {season} sem episódios exibidos")
            everything = set(aired_season)
            return (set(), everything) if everything <= watched else (everything, set())

        return await self._episode_action(series_id, season, choose)

    async def _episode_action(self, series_id: int, number: int, choose: Choice) -> SeasonView:
        detail = await self._catalog.detail(series_id)
        if number not in {s.number for s in detail.seasons}:
            raise InvalidAction(f"temporada {number}")
        season = await self._catalog.season(series_id, number)
        aired = _aired(detail)
        watched = self._repo.watched(series_id)
        add, remove = choose(self._season_aired(detail, season), aired, watched)
        marks = self._repo.marks(series_id)
        # especiais nunca mudam o status (spec §8)
        status = marks.status if number == 0 else auto_status(marks.status, aired, (watched | add) - remove)
        self._save(series_id, detail, status, marks.favorite, add=add, remove=remove,
                   runtimes=_runtimes(season, detail.typical_runtime))
        return self._view(series_id, detail, season)

    def _season_aired(self, detail: SeriesDetail, season: SeasonDetail) -> list[Ep]:
        if season.number == 0:
            return aired_specials(season.episodes, self._today())
        return season_episodes(_aired(detail), season.number)

    def _view(self, series_id: int, detail: SeriesDetail, season: SeasonDetail) -> SeasonView:
        watched = self._repo.watched(series_id)
        return SeasonView(
            detail=detail,
            season=season,
            marks=self._repo.marks(series_id),
            watched=frozenset(ep for ep in watched if ep[0] == season.number),
            aired=frozenset(self._season_aired(detail, season)),
            next_episode=next_episode(_aired(detail), watched),
        )

    def _save(self, series_id: int, detail: SeriesDetail, status: str | None, favorite: bool,
              add: Collection[Ep] = (), remove: Collection[Ep] = (), runtimes: dict[Ep, int | None] = {}) -> None:
        self._repo.save(series_id, name=detail.name, poster_path=detail.poster_path, status=status,
                        favorite=favorite, add=add, remove=remove, runtimes=runtimes)

    # Minhas séries
    async def my_series(self, tab: str) -> MySeries:
        tab = tab if tab in TABS else DEFAULT_TAB
        await self.fill_runtimes()
        counts = self._repo.counts()
        items = self._repo.list_tab(TABS[tab])
        if tab == "assistindo":
            semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)
            items = await asyncio.gather(*(self._with_next(item, semaphore) for item in items))
        return MySeries(tab, {url: counts[key] for url, key in TABS.items()}, tuple(items), self._repo.watch_time())

    def watch_time(self) -> tuple[int, int]:
        """(episódios marcados, minutos assistidos) para o contador."""
        return self._repo.watch_time()

    async def fill_runtimes(self) -> None:
        """Busca na TMDB a duração dos episódios marcados sem ela (ex.: marcados de uma vez com "Assistido")."""
        semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)
        missing = self._repo.missing_runtimes()
        await asyncio.gather(*(self._fill_series_runtimes(tmdb_id, seasons, semaphore)
                               for tmdb_id, seasons in missing.items()))

    async def _fill_series_runtimes(self, tmdb_id: int, numbers: set[int], semaphore: asyncio.Semaphore) -> None:
        async def fetch(call):
            try:
                async with semaphore:
                    return await call
            except TMDBError:
                return None

        detail = await fetch(self._catalog.detail(tmdb_id))
        typical = detail.typical_runtime if detail else None
        seasons = await asyncio.gather(*(fetch(self._catalog.season(tmdb_id, n)) for n in numbers))
        known: dict[Ep, int | None] = {}
        for season in filter(None, seasons):
            known |= _runtimes(season, typical)
        runtimes = {ep: known.get(ep) or typical for ep in self._repo.watched(tmdb_id) if ep[0] in numbers}
        self._repo.set_runtimes(tmdb_id, {ep: minutes for ep, minutes in runtimes.items() if minutes})

    async def _with_next(self, item: TrackedSeries, semaphore: asyncio.Semaphore) -> TrackedSeries:
        """Próximo episódio e progresso; se a TMDB falhar para esta série, o cartão segue sem eles."""
        try:
            async with semaphore:
                detail = await self._catalog.detail(item.tmdb_id)
        except TMDBError:
            return item
        aired = _aired(detail)
        watched = self._repo.watched(item.tmdb_id)
        upcoming = next_episode(aired, watched)
        return dataclasses.replace(item, next_episode=upcoming, progress=progress(aired, watched),
                                   caught_up=upcoming is None)
