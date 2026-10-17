"""TrackingRepository: todo o SQL das marcações."""

import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime

from app.mappers import image_url
from app.models import Marks, TrackedSeries

LOCAL_USER_ID = 1  # sem login nesta fase; na fase 2b vira o usuário logado

Ep = tuple[int, int]

_TAB_FILTERS = {
    "watching": "status = 'watching'",
    "want": "status = 'want'",
    "watched": "status = 'watched'",
    "favorite": "favorite = 1",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TrackingRepository:
    def __init__(self, conn: sqlite3.Connection, user_id: int = LOCAL_USER_ID,
                 now: Callable[[], datetime] = _utc_now) -> None:
        self._conn = conn
        self._user = user_id
        self._now = now

    def marks(self, tmdb_id: int) -> Marks:
        return self.marks_for([tmdb_id]).get(tmdb_id, Marks())

    def marks_for(self, tmdb_ids: Sequence[int]) -> dict[int, Marks]:
        """Marcações das séries que têm linha no banco (as demais ficam de fora)."""
        if not tmdb_ids:
            return {}
        placeholders = ",".join("?" * len(tmdb_ids))
        rows = self._conn.execute(
            f"SELECT tmdb_id, status, favorite FROM series_tracking WHERE user_id = ? AND tmdb_id IN ({placeholders})",
            (self._user, *tmdb_ids))
        return {tmdb_id: Marks(status, bool(favorite)) for tmdb_id, status, favorite in rows}

    def watched(self, tmdb_id: int) -> frozenset[Ep]:
        rows = self._conn.execute("SELECT season, episode FROM watched_episodes WHERE user_id = ? AND tmdb_id = ?",
                                  (self._user, tmdb_id))
        return frozenset((season, episode) for season, episode in rows)

    def save(self, tmdb_id: int, *, name: str, poster_path: str | None, status: str | None, favorite: bool,
             add: Iterable[Ep] = (), remove: Iterable[Ep] = (), runtimes: Mapping[Ep, int | None] = {}) -> None:
        """Grava episódios (com a duração, quando conhecida), status, favorito e snapshot numa transação;
        apaga a linha que ficou sem nada."""
        now = self._now().isoformat()
        key = (self._user, tmdb_id)
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO watched_episodes (user_id, tmdb_id, season, episode, watched_at, runtime)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [(*key, season, episode, now, runtimes.get((season, episode))) for season, episode in add])
            self._conn.executemany(
                "DELETE FROM watched_episodes WHERE user_id = ? AND tmdb_id = ? AND season = ? AND episode = ?",
                [(*key, season, episode) for season, episode in remove])
            self._conn.execute(
                "INSERT INTO series_tracking (user_id, tmdb_id, status, favorite, name, poster_path, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (user_id, tmdb_id) DO UPDATE SET status = excluded.status,"
                " favorite = excluded.favorite, name = excluded.name, poster_path = excluded.poster_path,"
                " updated_at = excluded.updated_at",
                (*key, status, int(favorite), name, poster_path, now))
            self._conn.execute(
                "DELETE FROM series_tracking WHERE user_id = ? AND tmdb_id = ? AND status IS NULL AND favorite = 0"
                " AND NOT EXISTS (SELECT 1 FROM watched_episodes w"
                " WHERE w.user_id = series_tracking.user_id AND w.tmdb_id = series_tracking.tmdb_id)", key)

    def counts(self) -> dict[str, int]:
        row = self._conn.execute(
            "SELECT SUM(status = 'watching'), SUM(status = 'want'), SUM(status = 'watched'), SUM(favorite)"
            " FROM series_tracking WHERE user_id = ?", (self._user,)).fetchone()
        return {tab: count or 0 for tab, count in zip(("watching", "want", "watched", "favorite"), row)}

    def list_tab(self, tab: str) -> list[TrackedSeries]:
        """Séries de uma aba (watching, want, watched ou favorite), das mexidas mais recentemente primeiro."""
        rows = self._conn.execute(
            "SELECT tmdb_id, name, poster_path, status, favorite FROM series_tracking"
            f" WHERE user_id = ? AND {_TAB_FILTERS[tab]} ORDER BY updated_at DESC", (self._user,))
        return [TrackedSeries(tmdb_id, name, image_url(poster_path, "w342"), Marks(status, bool(favorite)))
                for tmdb_id, name, poster_path, status, favorite in rows]

    # Contador de tempo assistido
    def watch_time(self) -> tuple[int, int]:
        """(episódios marcados, minutos somados dos que têm duração conhecida)."""
        episodes, minutes = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(runtime), 0) FROM watched_episodes WHERE user_id = ?",
            (self._user,)).fetchone()
        return episodes, minutes

    def missing_runtimes(self) -> dict[int, set[int]]:
        """Séries e temporadas com episódios marcados de duração ainda desconhecida."""
        missing: dict[int, set[int]] = {}
        rows = self._conn.execute("SELECT DISTINCT tmdb_id, season FROM watched_episodes"
                                  " WHERE user_id = ? AND runtime IS NULL", (self._user,))
        for tmdb_id, season in rows:
            missing.setdefault(tmdb_id, set()).add(season)
        return missing

    def set_runtimes(self, tmdb_id: int, runtimes: Mapping[Ep, int]) -> None:
        with self._conn:
            self._conn.executemany(
                "UPDATE watched_episodes SET runtime = ? WHERE user_id = ? AND tmdb_id = ? AND season = ?"
                " AND episode = ? AND runtime IS NULL",
                [(minutes, self._user, tmdb_id, season, episode) for (season, episode), minutes in runtimes.items()])
