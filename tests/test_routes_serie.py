import pytest

from app.models import WatchOptions
from app.tmdb.client import TMDBNotFound
from tests.fakes import FakeCatalog, make_detail


def test_detail_main_sections(make_client):
    t = make_client(FakeCatalog(detail=make_detail())).get("/serie/100088").text
    for s in ("The Last of Us", "2023–", "Em exibição", "Onde assistir no Brasil", "Assinatura", 'alt="Max"',
              "youtube-nocookie.com/embed/abc123", "Ver opções de streaming ↗",
              'href="https://www.themoviedb.org/tv/100088/watch?locale=BR"', "Disponibilidade fornecida pelo JustWatch.",
              "Temporada 1", "Pedro Pascal", "Joel", "history.back()", "← Voltar", "★ 8,6"):
        assert s in t, s


def test_without_trailer_and_providers(make_client):
    d = make_detail(trailer_youtube_key=None, watch=WatchOptions(None, {}))
    t = make_client(FakeCatalog(detail=d)).get("/serie/1").text
    assert "youtube-nocookie" not in t and "Ver opções de streaming" not in t
    assert "Não disponível em streaming no Brasil no momento" in t


def test_original_name_only_when_different(make_client):
    same = make_client(FakeCatalog(detail=make_detail(name="Xógum", original_name="Xógum"))).get("/serie/1").text
    assert "Shōgun" not in same
    different = make_client(FakeCatalog(detail=make_detail(name="Xógum", original_name="Shōgun"))).get("/serie/1").text
    assert "Shōgun" in different


def test_empty_overview_message(make_client):
    assert "Sinopse não disponível." in make_client(FakeCatalog(detail=make_detail(overview=""))).get("/serie/1").text


def test_passes_series_id(make_client):
    fake = FakeCatalog(detail=make_detail())
    make_client(fake).get("/serie/100088")
    assert ("detail", (100088,)) in fake.calls


def test_unknown_series_is_404(make_client):
    r = make_client(FakeCatalog(error=TMDBNotFound())).get("/serie/999")
    assert r.status_code == 404 and "Série não encontrada" in r.text


# Review Focus 5
@pytest.mark.parametrize("path", ["/serie/abc", "/serie/-5"])
def test_invalid_id_is_html_404(client, path):
    r = client.get(path)
    assert r.status_code == 404 and "text/html" in r.headers["content-type"] and "Página não encontrada" in r.text
