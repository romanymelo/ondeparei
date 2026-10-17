"""O "← Voltar" da página da série leva à última lista vista: catálogo (com filtros), busca ou Minhas séries."""

import re

import pytest

from starlette.requests import Request

from app.models import Marks, SeriesTracking
from app.templating import templates
from tests.fakes import HX, make_detail, make_page, tracked_catalog

ID = 100088


def back_link(html: str) -> str:
    return re.search(r'<a href="([^"]*)" class="voltar"[^>]*>', html).group(0)


@pytest.fixture
def c(make_client):
    fake = tracked_catalog()
    fake._results.update(discover=make_page(), search=make_page())
    return make_client(fake)


def test_without_a_list_goes_home(c):
    link = back_link(c.get(f"/serie/{ID}").text)
    assert 'href="/"' in link and "history.back" not in link


def test_after_search_goes_back_to_search(c):
    c.get("/buscar?q=the office")
    assert 'href="/buscar?q=the+office"' in back_link(c.get(f"/serie/{ID}").text)


def test_after_filtering_goes_back_to_filtered_catalog_without_page(c):
    c.get("/?servicos=8&nota=7")
    c.get("/?servicos=8&nota=7&pagina=2", headers=HX)  # "Carregar mais" não muda o destino
    assert 'href="/?servicos=8&amp;nota=7"' in back_link(c.get(f"/serie/{ID}").text)


def test_after_my_series_goes_back_to_my_series(c):
    c.get("/minhas-series?aba=quero")
    assert 'href="/minhas-series?aba=quero"' in back_link(c.get(f"/serie/{ID}").text)


def test_coming_from_a_season_still_goes_to_the_list(c):
    c.get("/buscar?q=last")
    page = c.get(f"/serie/{ID}", headers={"Referer": f"http://testserver/serie/{ID}/temporada/1"}).text
    link = back_link(page)
    assert 'href="/buscar?q=last"' in link and "history.back" not in link


def test_coming_straight_from_the_list_uses_browser_back_to_keep_scroll(c):
    c.get("/buscar?q=last")
    link = back_link(c.get(f"/serie/{ID}", headers={"Referer": "http://testserver/buscar?q=last"}).text)
    assert 'href="/buscar?q=last"' in link and "history.back()" in link


@pytest.mark.parametrize("cookie", ["//evil.example/", "https://evil.example/", "/serie/1", "javascript:alert(1)"])
def test_unsafe_or_unknown_cookie_falls_back_to_home(c, cookie):
    c.cookies.set("ultima_lista", cookie)
    assert 'href="/"' in back_link(c.get(f"/serie/{ID}").text)


def test_back_link_never_renders_empty_even_without_back_url():
    """Servidor com código antigo e template novo (sem --reload) não pode gerar um Voltar que não sai do lugar."""
    request = Request({"type": "http", "method": "GET", "path": "/serie/1", "headers": [], "query_string": b""})
    tracking = SeriesTracking(Marks(), None, None, {})
    html = templates.get_template("serie.html").render(request=request, serie=make_detail(), series_id=1,
                                                       tracking=tracking)
    assert 'href="/" class="voltar"' in html
