import re
import sqlite3

import pytest

from app.tmdb.client import TMDBUnavailable
from app.tracking.db import connect
from app.tracking.repository import TrackingRepository
from app.auth.client import User
from tests.fakes import HX, TEST_USER, FakeCatalog, make_detail, make_page, tracked_catalog, tracked_detail

ID = 100088


def seed(db, tmdb_id=ID, **kw):
    conn = connect(db)
    fields = {"name": "The Last of Us", "poster_path": None, "status": None, "favorite": False} | kw
    TrackingRepository(conn, user_id=TEST_USER.id).save(tmdb_id, **fields)
    conn.close()


def saved_marks(db):
    conn = connect(db)
    marks = TrackingRepository(conn, user_id=TEST_USER.id).marks_for([ID])
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


def test_season_page_lists_episodes(make_client):
    t = make_client(tracked_catalog()).get(f"/serie/{ID}/temporada/2").text
    assert 'id="ep-1"' in t and "E1 · Episódio 1" in t and "01/01/2023" in t and "0 de 2 assistidos" in t
    assert "Estreia em 01/01/2027" in t and 'name="episodio" value="3"' not in t
    assert "Marcar temporada inteira" in t and f'href="/serie/{ID}"' in t


def test_toggle_episode_with_htmx_updates_block(make_client):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/episodio", data={"temporada": 1, "episodio": 1},
                                            headers=HX)
    assert r.status_code == 200 and 'id="temporada"' in r.text and "<html" not in r.text
    assert "1 de 3 assistidos" in r.text and 'style="--pausa: 33%"' in r.text
    assert 'id="ep-2" class="episodio episodio--proximo"' in r.text


@pytest.mark.parametrize(("path", "body"), [
    ("/episodio", {"temporada": 1, "episodio": 2}),
    ("/ate-aqui", {"temporada": 1, "episodio": 2}),
    ("/temporada/1/toda", {}),
])
def test_episode_actions_without_htmx_redirect_to_season(make_client, path, body):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}{path}", data=body, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/serie/{ID}/temporada/1"


def test_whole_season_button_flips(make_client):
    t = make_client(tracked_catalog()).post(f"/serie/{ID}/temporada/1/toda", headers=HX).text
    assert "3 de 3 assistidos" in t and "Desmarcar temporada" in t


@pytest.mark.parametrize("body", [
    {"temporada": "1", "episodio": "abc"}, {"temporada": "1"}, {"temporada": "1", "episodio": "-1"},
    {"temporada": "1", "episodio": "1.5"}, {"temporada": "2", "episodio": "3"}, {"temporada": "9", "episodio": "1"},
    {"temporada": "1", "episodio": "²"},
])
def test_invalid_episode_is_400(make_client, body):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/episodio", data=body, headers=HX)
    assert r.status_code == 400 and "Ação inválida" in r.text


def test_unknown_season_page_is_404(make_client):
    r = make_client(tracked_catalog()).get(f"/serie/{ID}/temporada/9")
    assert r.status_code == 404 and "Página não encontrada" in r.text


def test_season_page_without_aired_episodes_has_no_actions(make_client):
    t = make_client(tracked_catalog(detail=tracked_detail(last_aired=None))).get(f"/serie/{ID}/temporada/1").text
    assert "Marcar temporada inteira" not in t and 'name="episodio"' not in t


def test_header_links_to_my_series(client):
    assert 'href="/minhas-series"' in client.get("/").text


def test_my_series_tabs_with_counts(make_client, tmp_path):
    db = tmp_path / "m.db"
    seed(db, status="watching", add=[(1, 1)])
    seed(db, 1399, name="Outra", status="want", favorite=True)
    details = {ID: tracked_detail(), 1399: tracked_detail(id=1399, name="Outra")}
    c = make_client(tracked_catalog(details=details), db=db)
    t = c.get("/minhas-series").text
    assert 'href="/minhas-series?aba=assistindo" aria-current="page"' in t
    assert t.count('<span class="contagem">1</span>') == 3 and '<span class="contagem">0</span>' in t
    assert "The Last of Us" in t and "Próximo: T1E2" in t and 'style="--pausa: 20%"' in t and "Outra" not in t
    t = c.get("/minhas-series?aba=quero").text
    assert "Outra" in t and "The Last of Us" not in t


def test_unknown_tab_shows_watching(make_client):
    t = make_client(tracked_catalog()).get("/minhas-series?aba=xyz").text
    assert 'href="/minhas-series?aba=assistindo" aria-current="page"' in t


def test_empty_tab_points_to_catalog(make_client):
    t = make_client(tracked_catalog()).get("/minhas-series?aba=favoritas").text
    assert "Nenhuma série aqui ainda." in t and "Explorar o catálogo" in t


def test_caught_up_series(make_client, tmp_path):
    db = tmp_path / "e.db"
    seed(db, status="watching", add=[(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)])
    assert "Em dia (aguardando episódios)" in make_client(tracked_catalog(), db=db).get("/minhas-series").text


def test_tmdb_down_on_action_saves_nothing(make_client, tmp_path):
    db = tmp_path / "c.db"
    c = make_client(tracked_catalog(error=TMDBUnavailable("fora")), db=db)
    r = c.post(f"/serie/{ID}/status", data={"status": "want"}, headers=HX)
    assert r.status_code == 200 and "A TMDB não respondeu" in r.text
    assert saved_marks(db) == {}


def test_catalog_more_and_search_show_badges(make_client, tmp_path):
    db = tmp_path / "s.db"
    seed(db, 1, name="Série 1", status="watching", favorite=True)
    c = make_client(FakeCatalog(discover=make_page(), search=make_page(), detail=make_detail()), db=db)
    for url, headers in [("/", {}), ("/?pagina=2", HX), ("/buscar?q=serie", {})]:
        t = c.get(url, headers=headers).text
        assert t.count('class="selo"') == 2, url
        assert 'aria-label="Assistindo"' in t and 'aria-label="Favorita"' in t


def test_controls_keep_ids_so_htmx_restores_keyboard_focus(make_client):
    c = make_client(tracked_catalog())
    status = c.post(f"/serie/{ID}/status", data={"status": "watching"}, headers=HX).text
    assert all(f'id="status-{v}"' in status for v in ("want", "watching", "watched")) and 'id="favorita"' in status
    season = c.post(f"/serie/{ID}/episodio", data={"temporada": 1, "episodio": 1}, headers=HX).text
    assert 'id="marcar-1-1"' in season and 'id="marcar-1-3"' in season and 'id="temporada-toda"' in season


@pytest.mark.parametrize("url", [f"/serie/{ID}", f"/serie/{ID}/temporada/1", "/minhas-series"])
def test_pages_with_marks_are_not_kept_in_back_forward_cache(make_client, url):
    assert make_client(tracked_catalog()).get(url).headers["cache-control"] == "no-store"


def test_marking_watched_fills_the_season_cards(make_client):
    c = make_client(tracked_catalog())
    c.post(f"/serie/{ID}/status", data={"status": "watched"})
    t = c.get(f"/serie/{ID}").text
    assert t.count('style="--pausa: 100%"') == 2 and "3/3" in t and "2/2" in t


def test_my_series_shows_the_watch_time_counter(make_client, tmp_path):
    db = tmp_path / "t.db"
    episodes = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)]
    seed(db, status="watched", add=episodes, runtimes={ep: 50 for ep in episodes})  # 250 min
    t = make_client(tracked_catalog(), db=db).get("/minhas-series?aba=assistidas").text
    placas = re.findall(r'<span class="placa"[^>]*>(\d)</span>', t)
    assert placas == ["0", "0", "0", "0", "0", "4"]  # meses, dias, horas
    assert "meses" in t and "dias" in t and "horas" in t
    assert '<p class="sr-only">4 horas em 5 episódios</p>' in t
    assert '<strong class="placar-numero">5</strong>' in t


def test_watch_time_counter_with_nothing_watched(make_client):
    t = make_client(tracked_catalog()).get("/minhas-series").text
    assert '<p class="sr-only">0 horas em 0 episódios</p>' in t


def test_stylesheet_url_changes_with_the_file_so_browsers_reload_it(client):
    assert re.search(r'href="/static/style\.css\?v=\d+"', client.get("/").text)


# Contador também no cabeçalho
@pytest.mark.xfail(strict=True, reason="Task 7: contador do cabeçalho por conta")
def test_header_shows_the_watch_time_and_links_to_my_series(make_client, tmp_path):
    db = tmp_path / "h.db"
    episodes = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)]
    seed(db, status="watched", add=episodes, runtimes={ep: 50 for ep in episodes})  # 250 min
    t = make_client(tracked_catalog(discover=make_page()), db=db).get("/").text
    header = t.split("</header>")[0]
    assert 'class="contador-topo contador-topo--anima" href="/minhas-series"' in header
    assert re.findall(r'<span class="placa-mini"[^>]*>(\d)</span>', header) == ["0", "4"]
    assert "Tempo de séries: 4 horas" in header


@pytest.mark.xfail(strict=True, reason="Task 7: contador do cabeçalho por conta")
def test_header_counter_does_not_animate_outside_home(make_client, tmp_path):
    db = tmp_path / "h.db"
    seed(db, status="watched", add=[(1, 1)], runtimes={(1, 1): 120})
    header = make_client(tracked_catalog(), db=db).get(f"/serie/{ID}").text.split("</header>")[0]
    assert 'class="contador-topo" href="/minhas-series"' in header


def test_header_hides_the_counter_with_nothing_watched(make_client):
    assert "contador-topo" not in make_client(tracked_catalog(discover=make_page())).get("/").text


@pytest.mark.xfail(strict=True, reason="Task 7: contador do cabeçalho por conta")
def test_marking_watched_fills_runtimes_right_after_the_click(make_client):
    c = make_client(tracked_catalog(discover=make_page()))
    c.post(f"/serie/{ID}/status", data={"status": "watched"})  # 5 episódios, duração buscada depois da resposta
    assert "Tempo de séries: 4 horas" in c.get("/").text


# Visitante e contas separadas
def test_visitor_browses_series_and_season_without_marks(make_client):
    c = make_client(tracked_catalog(), user=None)
    page = c.get(f"/serie/{ID}")
    assert page.status_code == 200 and 'value="want" aria-pressed="false"' in page.text
    assert 'aria-pressed="true"' not in c.get(f"/serie/{ID}/temporada/1").text


def test_visitor_sees_no_badges(make_client, tmp_path):
    db = tmp_path / "v.db"
    seed(db, 1, name="Série 1", status="watching", favorite=True)
    t = make_client(FakeCatalog(discover=make_page(), search=make_page(), detail=make_detail()), db=db, user=None).get("/").text
    assert 'class="selo"' not in t


def test_two_users_do_not_see_each_other(make_client, tmp_path):
    db = tmp_path / "dois.db"
    make_client(tracked_catalog(), db=db).post(f"/serie/{ID}/status", data={"status": "want"})
    other = User("00000000-0000-0000-0000-000000000002", "outro@teste.com", "Ana", "Silva")
    page = make_client(tracked_catalog(), db=db, user=other).get(f"/serie/{ID}").text
    assert 'value="want" aria-pressed="true"' not in page
