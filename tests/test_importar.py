import json

import httpx
import pytest
import respx

from app.importar import Summary, import_local, main
from app.tracking.db import connect
from app.tracking.repository import TrackingRepository

URL = "https://proj.supabase.co"
UID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def local_db(tmp_path):
    path = tmp_path / "catalogo.db"
    conn = connect(path)
    repo = TrackingRepository(conn)
    repo.save(1396, name="Breaking Bad", poster_path="/bb.jpg", status="watched", favorite=True,
              add=[(1, 1), (1, 2)], runtimes={(1, 1): 58, (1, 2): 48})
    repo.save(153312, name="Tulsa King", poster_path=None, status="watching", favorite=False, add=[(1, 1)])
    conn.close()
    return path


@pytest.fixture
def mock():
    with respx.mock(base_url=URL, assert_all_called=False) as m:
        m.get("/auth/v1/admin/users", params={"page": "1"}).respond(
            json={"users": [{"id": "outro", "email": "outro@x.com"}]})
        m.get("/auth/v1/admin/users", params={"page": "2"}).respond(json={"users": [{"id": UID, "email": "Eu@Teste.com"}]})
        m.get("/auth/v1/admin/users", params={"page": "3"}).respond(json={"users": []})
        m.post("/rest/v1/series_tracking").respond(201)
        m.post("/rest/v1/watched_episodes").respond(201)
        m.get("/rest/v1/watched_episodes").respond(json=[{"runtime": 58}, {"runtime": 48}, {"runtime": None}])
        yield m


async def run(local_db, email="eu@teste.com"):
    async with httpx.AsyncClient(timeout=10) as http:
        return await import_local(local_db, email, http, URL, "sb_secret_x")


async def test_imports_with_upsert_and_user_id(local_db, mock):
    summary = await run(local_db)
    assert summary == Summary(series=2, episodes=3, minutes_before=106, minutes_after=106)
    series = mock.routes[3].calls.last.request
    assert series.url.params["on_conflict"] == "user_id,tmdb_id"
    assert "resolution=ignore-duplicates" in series.headers["prefer"] and series.headers["apikey"] == "sb_secret_x"
    totals = mock.routes[5].calls.last.request.url.params
    assert totals["order"] == "tmdb_id,season,episode"
    rows = sorted(json.loads(series.content), key=lambda r: r["tmdb_id"])
    assert rows[0] | {"updated_at": None} == {"user_id": UID, "tmdb_id": 1396, "status": "watched", "favorite": True,
                                             "name": "Breaking Bad", "poster_path": "/bb.jpg", "updated_at": None}
    episodes = mock.routes[4].calls.last.request
    assert episodes.url.params["on_conflict"] == "user_id,tmdb_id,season,episode"
    first = sorted(json.loads(episodes.content), key=lambda r: (r["tmdb_id"], r["season"], r["episode"]))[0]
    assert {k: first[k] for k in ("user_id", "tmdb_id", "season", "episode", "runtime")} == {
        "user_id": UID, "tmdb_id": 1396, "season": 1, "episode": 1, "runtime": 58}


async def test_lookup_is_paginated_and_case_insensitive(local_db, mock):
    await run(local_db, "EU@TESTE.COM")
    assert mock.routes[1].called and not mock.routes[2].called


async def test_account_not_found(local_db, mock):
    with pytest.raises(LookupError, match="Conta não encontrada: crie a conta no app primeiro."):
        await run(local_db, "ninguem@x.com")


async def test_running_twice_sends_the_same_upserts(local_db, mock):
    await run(local_db)
    first = mock.routes[4].calls.last.request.content
    await run(local_db)
    assert mock.routes[4].calls.last.request.content == first


def test_main_requires_the_secret_key(monkeypatch, capsys):
    monkeypatch.setenv("TMDB_TOKEN", "x")
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "pk")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    assert main(["eu@teste.com"], env_file=None) == 2
    assert "SUPABASE_SECRET_KEY não definido no .env (necessário só para a importação)." in capsys.readouterr().err
