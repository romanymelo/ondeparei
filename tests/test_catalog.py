import asyncio
from datetime import date

import httpx
import pytest
import respx

from app.catalog import Catalog
from app.models import Filters
from app.tmdb.cache import TTLCache
from app.tmdb.client import BASE_URL, TMDBClient, TMDBNotFound, create_http_client
from tests.helpers import load_fixture


@pytest.fixture
async def catalog():
    http = create_http_client("t")
    yield Catalog(TMDBClient(http, TTLCache()), "BR", "pt-BR", today=lambda: date(2026, 10, 16))
    await http.aclose()


@pytest.fixture
def mock():
    with respx.mock(base_url=BASE_URL) as m:
        yield m


async def test_discover_sends_translated_params(catalog, mock):
    data = load_fixture("discover.json")
    route = mock.get("/discover/tv").respond(json=data)
    page = await catalog.discover(Filters(providers=(8,), sort="nota"))
    for call in route.calls:
        params = call.request.url.params
        assert params["with_watch_providers"] == "8" and params["vote_count.gte"] == "50"
        assert params["watch_region"] == "BR"
    assert page.items[0].id == data["results"][0]["id"]


def tmdb_page(n: int, total_results: int) -> dict:
    """Página n da TMDB (20 por página) de um resultado com `total_results` séries numeradas a partir de 1."""
    first = (n - 1) * 20 + 1
    last = min(n * 20, total_results)
    results = [{"id": i, "name": f"S{i}", "first_air_date": "", "vote_average": 0, "vote_count": 0,
                "poster_path": None} for i in range(first, last + 1)]
    return {"page": n, "total_pages": -(-total_results // 20), "total_results": total_results, "results": results}


def mock_discover(mock, total_results: int):
    def respond(request):
        return httpx.Response(200, json=tmdb_page(int(request.url.params["page"]), total_results))
    return mock.get("/discover/tv").mock(side_effect=respond)


def requested_pages(route) -> list[int]:
    return sorted(int(call.request.url.params["page"]) for call in route.calls)


async def test_first_page_joins_three_tmdb_pages(catalog, mock):
    route = mock_discover(mock, total_results=16000)
    page = await catalog.discover(Filters())
    assert requested_pages(route) == [1, 2, 3]
    assert [c.id for c in page.items] == list(range(1, 51)) and page.page == 1


async def test_second_page_continues_at_51(catalog, mock):
    route = mock_discover(mock, total_results=16000)
    page = await catalog.discover(Filters(page=2))
    assert requested_pages(route) == [3, 4, 5]
    assert [c.id for c in page.items] == list(range(51, 101)) and page.page == 2


@pytest.mark.parametrize("total_results, total_pages", [(16000, 200), (120, 3), (50, 1), (0, 0)])
async def test_total_pages_counts_50_per_page(catalog, mock, total_results, total_pages):
    mock_discover(mock, total_results=total_results)
    page = await catalog.discover(Filters())
    assert (page.total_results, page.total_pages) == (total_results, total_pages)


async def test_few_results_do_not_request_missing_pages(catalog, mock):
    route = mock_discover(mock, total_results=35)
    page = await catalog.discover(Filters())
    assert requested_pages(route) == [1, 2]
    assert len(page.items) == 35 and page.total_pages == 1


async def test_page_beyond_tmdb_cap_requests_nothing_above_500(catalog, mock):
    route = mock_discover(mock, total_results=16000)
    page = await catalog.discover(Filters(page=201))
    assert max(requested_pages(route)) <= 500
    assert page.items == () and page.total_pages == 200


async def test_providers_and_genres(catalog, mock):
    mock.get("/watch/providers/tv").respond(json=load_fixture("providers_tv.json"))
    mock.get("/genre/tv/list").respond(json=load_fixture("genres_tv.json"))
    assert len(await catalog.providers()) == 15
    assert all(g.name for g in await catalog.genres())


async def test_search_attaches_providers_per_card(catalog, mock):
    data = load_fixture("search_office.json")
    ids = [r["id"] for r in data["results"]]
    mock.get("/search/tv").respond(json=data)
    mock.get(f"/tv/{ids[0]}/watch/providers").respond(json={"id": ids[0], "results": {"BR": {"flatrate": [
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/n.png", "display_priority": 0}]}}})
    mock.get(f"/tv/{ids[1]}/watch/providers").respond(json={"id": ids[1], "results": {}})
    mock.get(f"/tv/{ids[2]}/watch/providers").respond(500)
    page = await catalog.search("office", 1)
    assert [c.providers is None for c in page.items] == [False, False, True]
    assert page.items[0].providers[0].name == "Netflix" and page.items[1].providers == ()


async def test_search_limits_concurrency(catalog, mock):
    results = [{"id": i, "name": f"S{i}", "first_air_date": "", "vote_average": 0, "vote_count": 0,
                "poster_path": None} for i in range(1, 21)]
    mock.get("/search/tv").respond(json={"page": 1, "total_pages": 1, "total_results": 20, "results": results})
    in_flight = peak = 0

    async def slow(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json={"results": {}})

    route = mock.get(url__regex=r"/tv/\d+/watch/providers").mock(side_effect=slow)
    await catalog.search("s", 1)
    assert route.call_count == 20 and peak <= 10


async def test_search_truncates_query(catalog, mock):
    route = mock.get("/search/tv").respond(json={"page": 1, "total_pages": 0, "total_results": 0, "results": []})
    await catalog.search("a" * 150, 1)
    assert route.calls.last.request.url.params["query"] == "a" * 100


async def test_detail_uses_append_to_response(catalog, mock):
    route = mock.get("/tv/100088").respond(json=load_fixture("tv_100088.json"))
    d = await catalog.detail(100088)
    params = route.calls.last.request.url.params
    assert params["append_to_response"] == "aggregate_credits,videos,watch/providers"
    assert params["include_video_language"] == "pt,en,null" and params["language"] == "pt-BR"
    assert d.id == 100088


async def test_detail_falls_back_to_english_overview(catalog, mock):
    data = load_fixture("tv_100088.json")
    data["overview"] = ""
    mock.get("/tv/100088", params__contains={"language": "en-US"}).respond(json={"overview": "English text"})
    mock.get("/tv/100088", params__contains={"language": "pt-BR"}).respond(json=data)
    assert (await catalog.detail(100088)).overview == "English text"


async def test_detail_fallback_failure_is_ignored(catalog, mock):
    data = load_fixture("tv_100088.json")
    data["overview"] = ""
    mock.get("/tv/100088", params__contains={"language": "en-US"}).respond(503)
    mock.get("/tv/100088", params__contains={"language": "pt-BR"}).respond(json=data)
    assert (await catalog.detail(100088)).overview == ""


async def test_detail_not_found_propagates(catalog, mock):
    mock.get("/tv/1").respond(404)
    with pytest.raises(TMDBNotFound):
        await catalog.detail(1)


# Revisão final #6: spec §8.3 — falha na consulta de um cartão não derruba a busca
async def test_search_card_with_invalid_json_keeps_page(catalog, mock):
    data = load_fixture("search_office.json")
    mock.get("/search/tv").respond(json=data)
    mock.get(url__regex=r"/tv/\d+/watch/providers").respond(200, content=b"nao e json")
    page = await catalog.search("office", 1)
    assert len(page.items) == 3 and all(c.providers is None for c in page.items)
