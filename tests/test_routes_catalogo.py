import re

import pytest

from app.models import Filters, Genre, Provider
from app.routes import next_page_url
from app.tmdb.client import TMDBUnavailable
from tests.fakes import HX, FakeCatalog, make_page


@pytest.fixture
def fake():
    return FakeCatalog(discover=make_page(n=3, page=1, total_pages=2, total_results=1284),
                       providers=(Provider(8, "Netflix", None),), genres=(Genre(18, "Drama"),))


def test_full_page(client):
    t = client.get("/").text
    assert 'id="filtros"' in t and 'hx-target="#grade"' in t and 'hx-push-url="true"' in t
    assert "Netflix" in t and "Drama" in t and "1.284 séries" in t and "Carregar mais" in t
    assert 'for="mostrar-filtros"' in t and "Filtros (0)" in t


def test_htmx_first_page_returns_grid_fragment(client):
    t = client.get("/", headers=HX).text
    assert "<html" not in t and 'class="contador"' in t


def test_htmx_next_page_returns_only_cards(make_client):
    t = make_client(FakeCatalog(discover=make_page(page=2, total_pages=3))).get("/?servicos=8&pagina=2", headers=HX).text
    assert 'class="contador"' not in t and "Série 1" in t and "servicos=8" in t and "pagina=3" in t


def test_next_page_url():
    assert next_page_url("/", [("servicos", "8"), ("servicos", "1899"), ("pagina", "1")], 2) == \
        "/?servicos=8&servicos=1899&pagina=2"
    assert next_page_url("/buscar", [("q", "café & cia")], 2) == "/buscar?q=caf%C3%A9+%26+cia&pagina=2"


def test_invalid_query_uses_defaults(client, fake):
    assert client.get("/?servicos=abc&nota=99&pagina=x").status_code == 200
    assert ("discover", (Filters(),)) in fake.calls


def test_filters_prefilled(client):
    t = client.get("/?servicos=8&nota=7&generos=18").text
    assert 'name="servicos" value="8" checked' in t and 'value="7" selected' in t
    assert 'name="generos" value="18" checked' in t
    assert "Filtros (3)" in t


def test_only_service_genre_and_rating_filters(client):
    t = client.get("/").text
    assert 'name="servicos"' in t and 'name="generos"' in t and 'name="nota"' in t
    assert 'name="tipos"' not in t and 'name="ano_de"' not in t and 'name="ano_ate"' not in t
    assert "Ano de estreia" not in t


def test_old_links_with_removed_filters_still_work(client, fake):
    assert client.get("/?tipos=rent&ano_de=2015&ano_ate=2020").status_code == 200
    assert ("discover", (Filters(),)) in fake.calls


def test_provider_list_failure_still_renders(make_client):
    r = make_client(FakeCatalog(discover=make_page(), providers_error=TMDBUnavailable())).get("/")
    assert r.status_code == 200 and "indisponível no momento" in r.text


def test_discover_error_in_htmx_is_fragment(make_client):
    r = make_client(FakeCatalog(error=TMDBUnavailable())).get("/", headers=HX)
    assert r.status_code == 200 and "A TMDB não respondeu" in r.text


def test_empty_results_message(make_client):
    t = make_client(FakeCatalog(discover=make_page(n=0, total_pages=0, total_results=0))).get("/").text
    assert "Nenhuma série encontrada com esses filtros." in t and "Carregar mais" not in t


# Review Focus 4
def test_page_beyond_total_has_no_button(make_client):
    r = make_client(FakeCatalog(discover=make_page(n=0, page=7, total_pages=3, total_results=50))).get(
        "/?pagina=7", headers=HX)
    assert r.status_code == 200 and "Carregar mais" not in r.text


def test_providers_beyond_12_go_into_details(make_client):
    providers = tuple(Provider(i, f"Serviço {i}", None) for i in range(1, 16))
    c = make_client(FakeCatalog(discover=make_page(), providers=providers))
    closed = c.get("/").text
    assert re.search(r"<details>\s*<summary>ver todos \(15\)</summary>", closed)
    opened = c.get("/?servicos=13").text
    assert re.search(r"<details open>\s*<summary>ver todos \(15\)</summary>", opened)
    assert 'name="servicos" value="13" checked' in opened


# Revisão final #1: voltar/avançar do navegador com HTMX
def test_base_disables_htmx_history_snapshots(client):
    t = client.get("/").text
    assert re.search(r'<meta name="htmx-config" content=\'\{"historyCacheSize":\s*0,\s*"refreshOnHistoryMiss":\s*true\}\'>', t)


def test_history_restore_request_gets_full_page(client):
    t = client.get("/?servicos=8", headers={"HX-Request": "true", "HX-History-Restore-Request": "true"}).text
    assert "<html" in t and 'id="filtros"' in t


@pytest.mark.parametrize("path", ["/", "/buscar?q=office"])
def test_pages_vary_on_hx_request(make_client, path):
    c = make_client(FakeCatalog(discover=make_page(), search=make_page()))
    assert "HX-Request" in c.get(path).headers.get("vary", "")
    assert "HX-Request" in c.get(path, headers=HX).headers.get("vary", "")


# Revisão final #2: ano inválido não pode travar o formulário (htmx valida o form antes de enviar)
def test_filter_form_skips_browser_validation(client):
    assert re.search(r'<form id="filtros"[^>]*\bnovalidate\b', client.get("/").text)
