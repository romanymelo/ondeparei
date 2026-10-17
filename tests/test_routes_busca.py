from app.models import CatalogPage, Provider
from tests.fakes import HX, FakeCatalog, make_card, make_page


def test_blank_query_redirects_home(client):
    r = client.get("/buscar?q=%20%20", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_results_page_with_notice(make_client):
    c = make_client(FakeCatalog(search=make_page(n=3, total_results=3)))
    t = c.get("/buscar?q=office").text
    assert '3 resultados para "office" · a busca ignora os filtros do catálogo' in t
    assert 'value="office"' in t


def test_singular_and_empty(make_client):
    one = make_client(FakeCatalog(search=make_page(n=1, total_results=1))).get("/buscar?q=x").text
    assert '1 resultado para "x"' in one
    none = make_client(FakeCatalog(search=make_page(n=0, total_results=0))).get("/buscar?q=x").text
    assert 'Nenhuma série encontrada para "x".' in none


def test_card_availability_states(make_client):
    netflix = Provider(8, "Netflix", "https://image.tmdb.org/t/p/w92/n.png")
    cards = (make_card(1, "Com", providers=(netflix,)), make_card(2, "Sem", providers=()),
             make_card(3, "Falhou", providers=None))
    t = make_client(FakeCatalog(search=CatalogPage(cards, 1, 1, 3))).get("/buscar?q=s").text
    assert t.count("Fora do streaming no BR") == 1 and t.count("esmaecido") == 1 and 'alt="Netflix"' in t


def test_passes_query_and_page(make_client):
    fake = FakeCatalog(search=make_page())
    make_client(fake).get("/buscar?q=office&pagina=2", headers=HX)
    assert ("search", ("office", 2)) in fake.calls


def test_htmx_next_page_returns_only_cards(make_client):
    t = make_client(FakeCatalog(search=make_page(page=2, total_pages=3))).get("/buscar?q=office&pagina=2",
                                                                            headers=HX).text
    assert "<html" not in t and "resultados para" not in t and "Série 1" in t and "pagina=3" in t


# Review Focus 3
def test_query_is_escaped(make_client):
    t = make_client(FakeCatalog(search=make_page(n=0, total_results=0))).get(
        "/buscar", params={"q": "<script>alert(1)</script>"}).text
    assert "<script>alert(1)</script>" not in t and "&lt;script&gt;" in t


def test_next_page_link_encodes_query(make_client):
    t = make_client(FakeCatalog(search=make_page(total_pages=2))).get("/buscar", params={"q": "café & cia"}).text
    assert "/buscar?q=caf%C3%A9+%26+cia&amp;pagina=2" in t
