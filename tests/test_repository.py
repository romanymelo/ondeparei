import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Marks
from app.tracking.db import MIGRATIONS, connect
from app.tracking.repository import TrackingRepository


class Ticks:
    """Relógio que avança 1 s a cada leitura."""

    def __init__(self):
        self.t = datetime(2026, 10, 17, tzinfo=UTC)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "t.db")
    yield TrackingRepository(conn, now=Ticks())
    conn.close()


def save(repo, tmdb_id, status=None, favorite=False, **kw):
    repo.save(tmdb_id, name=f"S{tmdb_id}", poster_path=f"/{tmdb_id}.jpg", status=status, favorite=favorite, **kw)


def test_connect_creates_folder_and_migrates(tmp_path):
    conn = connect(tmp_path / "data" / "x.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"series_tracking", "watched_episodes"} <= tables
    conn.close()


def test_marks_survive_reopening(tmp_path):
    path = tmp_path / "t.db"
    conn = connect(path)
    save(TrackingRepository(conn), 1, "want", favorite=True)
    conn.close()
    conn = connect(path)
    assert TrackingRepository(conn).marks(1) == Marks("want", True)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    conn.close()


def test_unmarked_series_has_empty_marks(repo):
    assert repo.marks(99) == Marks()


def test_episodes_add_remove_and_repeat(repo):
    save(repo, 1, "watching", add=[(1, 1), (1, 2)])
    save(repo, 1, "watching", add=[(1, 2)], remove=[(1, 1)])  # repetir não dá erro
    assert repo.watched(1) == frozenset({(1, 2)})


def test_marks_for_returns_only_tracked(repo):
    save(repo, 1, "watching")
    save(repo, 2, favorite=True)
    assert repo.marks_for([1, 2, 3]) == {1: Marks("watching", False), 2: Marks(None, True)}
    assert repo.marks_for([]) == {}


def test_tabs_counts_and_order(repo):
    save(repo, 1, "watching")
    save(repo, 2, "watched", favorite=True)
    save(repo, 3, "watching")
    assert [s.tmdb_id for s in repo.list_tab("watching")] == [3, 1]
    assert [s.tmdb_id for s in repo.list_tab("favorite")] == [2]
    assert repo.counts() == {"watching": 2, "want": 0, "watched": 1, "favorite": 1}
    item = repo.list_tab("watched")[0]
    assert (item.name, item.poster_url) == ("S2", "https://image.tmdb.org/t/p/w342/2.jpg")


def test_updating_moves_series_to_top(repo):
    save(repo, 1, "watching")
    save(repo, 2, "watching")
    save(repo, 1, "watching")
    assert [s.tmdb_id for s in repo.list_tab("watching")] == [1, 2]


def test_row_without_marks_is_deleted(repo):
    save(repo, 1, "want")
    save(repo, 1, None)
    assert repo.marks_for([1]) == {} and repo.counts()["want"] == 0
    save(repo, 2, None, add=[(0, 1)])  # um especial marcado mantém a linha
    assert repo.watched(2) == frozenset({(0, 1)}) and 2 in repo.marks_for([2])


def test_unknown_status_is_refused(repo):
    with pytest.raises(sqlite3.IntegrityError):
        save(repo, 1, "xyz")


def test_runtimes_are_stored_summed_and_repaired(repo):
    save(repo, 1, "watching", add=[(1, 1), (1, 2), (0, 1)], runtimes={(1, 1): 50, (0, 1): 20})
    save(repo, 2, "watched", add=[(1, 1)], runtimes={(1, 1): 30})
    assert repo.watch_time() == (4, 100)
    assert repo.missing_runtimes() == {1: {1}}
    repo.set_runtimes(1, {(1, 2): 45})
    assert repo.watch_time() == (4, 145) and repo.missing_runtimes() == {}


def test_version_1_database_gains_the_runtime_column(tmp_path):
    path = tmp_path / "v1.db"
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0] + "PRAGMA user_version = 1;")
    conn.execute("INSERT INTO watched_episodes (tmdb_id, season, episode, watched_at) VALUES (1, 1, 1, 'x')")
    conn.commit()
    conn.close()
    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) >= 2
    assert TrackingRepository(conn).missing_runtimes() == {1: {1}}
    conn.close()
