import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError
from app.main import create_app
from app.templating import format_rating, format_thousands
from app.tmdb.client import TMDBAuthError, TMDBNotFound, TMDBUnavailable
from tests.fakes import FakeCatalog

ERRORS = {"unavailable": TMDBUnavailable, "auth": TMDBAuthError, "notfound": TMDBNotFound}


@pytest.fixture
def boom_client():
    app = create_app(catalog=FakeCatalog())

    async def boom(kind: str):
        raise ERRORS[kind]()

    app.add_api_route("/boom/{kind}", boom)
    with TestClient(app) as c:
        yield c


def test_unknown_route_renders_html_404(client):
    r = client.get("/nao-existe")
    assert r.status_code == 404 and "text/html" in r.headers["content-type"] and "Página não encontrada" in r.text


def test_layout_has_attributions_search_and_htmx(client):
    t = client.get("/nao-existe").text
    assert "Este produto usa a API da TMDB, mas não é endossado nem certificado pela TMDB." in t
    assert "Dados de disponibilidade: JustWatch" in t and 'src="/static/tmdb-logo.svg"' in t
    assert 'action="/buscar"' in t and 'src="/static/htmx.min.js?v=' in t and "OndeParei" in t and "SériesBR" not in t


@pytest.mark.parametrize("kind, status, text", [
    ("unavailable", 503, "A TMDB não respondeu. Tente novamente em instantes."),
    ("auth", 502, "Problema de configuração com a TMDB (token inválido)"),
    ("notfound", 404, "Série não encontrada"),
])
def test_tmdb_errors_full_page(boom_client, kind, status, text):
    r = boom_client.get(f"/boom/{kind}")
    assert r.status_code == status and text in r.text and "<html" in r.text


def test_tmdb_error_htmx_fragment(boom_client):
    r = boom_client.get("/boom/unavailable",
                        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/?nota=7"})
    assert r.status_code == 200 and "<html" not in r.text
    assert "A TMDB não respondeu" in r.text and "Tentar novamente" in r.text and "/?nota=7" in r.text


def test_static_files_served(client):
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/tmdb-logo.svg").status_code == 200


def test_missing_token_fails_startup(monkeypatch, tmp_path):
    monkeypatch.delenv("TMDB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        with TestClient(create_app()):
            pass


@pytest.mark.parametrize("n, s", [(1284, "1.284"), (12, "12"), (1234567, "1.234.567")])
def test_format_thousands(n, s):
    assert format_thousands(n) == s


def test_format_rating():
    assert format_rating(8.64) == "8,6"


def test_footer_signature_keeps_required_attribution(client):
    t = client.get("/").text.split("<footer")[1]
    assert 'Desenvolvido sob o efeito de "só mais um episódio" por Romany Melo 📺✨' in t.replace("&#34;", '"')
    assert "não é endossado nem certificado pela TMDB" in t and "JustWatch" in t
