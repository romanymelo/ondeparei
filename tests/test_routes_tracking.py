import sqlite3

import pytest

from app.tmdb.client import TMDBUnavailable
from app.tracking.db import connect
from app.tracking.repository import TrackingRepository
from tests.fakes import HX, tracked_catalog, tracked_detail

ID = 100088


def seed(db, tmdb_id=ID, **kw):
    conn = connect(db)
    fields = {"name": "The Last of Us", "poster_path": None, "status": None, "favorite": False} | kw
    TrackingRepository(conn).save(tmdb_id, **fields)
    conn.close()


def saved_marks(db):
    conn = connect(db)
    marks = TrackingRepository(conn).marks_for([ID])
    conn.close()
    return marks


def test_status_survives_restart(make_client, tmp_path):
    db = tmp_path / "persistente.db"
    r = make_client(tracked_catalog(), db=db).post(f"/serie/{ID}/status", data={"status": "want"},
                                                   follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/serie/{ID}"
    page = make_client(tracked_catalog(), db=db).get(f"/serie/{ID}").text
    assert 'value="want" aria-pressed="true"' in page


def test_status_with_htmx_returns_only_the_block(make_client):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/status", data={"status": "watching"}, headers=HX)
    assert r.status_code == 200 and 'id="status-serie"' in r.text and "<html" not in r.text
    assert "Próximo: T1E1 — Episódio 1" in r.text


def test_favorite_toggles(make_client):
    c = make_client(tracked_catalog())
    assert 'class="favorita" aria-pressed="true"' in c.post(f"/serie/{ID}/favorito", headers=HX).text
    assert 'class="favorita" aria-pressed="false"' in c.post(f"/serie/{ID}/favorito", headers=HX).text


@pytest.mark.parametrize("body", [{"status": "xyz"}, {}])
def test_invalid_status_is_400(make_client, body):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/status", data=body, headers=HX)
    assert r.status_code == 400 and "Ação inválida" in r.text


def test_season_cards_link_and_show_progress(make_client, tmp_path):
    db = tmp_path / "c.db"
    seed(db, status="watching", add=[(1, 1)])
    t = make_client(tracked_catalog(), db=db).get(f"/serie/{ID}").text
    assert f'href="/serie/{ID}/temporada/1"' in t and 'style="--pausa: 33%"' in t
    assert "1/3" in t and "0/2" in t
    assert "Próximo: T1E2 — Episódio 2" in t


def test_series_without_aired_episodes_says_soon(make_client):
    t = make_client(tracked_catalog(detail=tracked_detail(last_aired=None))).get(f"/serie/{ID}").text
    assert t.count("Em breve") == 2 and "--pausa" not in t.split('class="temporadas"')[1]


def test_save_failure_shows_friendly_message(make_client, monkeypatch):
    def broken_save(self, *args, **kwargs):
        raise sqlite3.OperationalError("disco cheio")

    monkeypatch.setattr(TrackingRepository, "save", broken_save)
    c = make_client(tracked_catalog())
    r = c.post(f"/serie/{ID}/status", data={"status": "want"}, headers=HX)
    assert r.status_code == 200 and "Não foi possível salvar sua marcação. Tente novamente." in r.text
    assert c.post(f"/serie/{ID}/status", data={"status": "want"}).status_code == 500


def test_tmdb_down_on_action_saves_nothing(make_client, tmp_path):
    db = tmp_path / "c.db"
    c = make_client(tracked_catalog(error=TMDBUnavailable("fora")), db=db)
    r = c.post(f"/serie/{ID}/status", data={"status": "want"}, headers=HX)
    assert r.status_code == 200 and "A TMDB não respondeu" in r.text
    assert saved_marks(db) == {}
