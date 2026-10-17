import logging

import httpx
import pytest
import respx

from app.tmdb.cache import TTLCache
from app.tmdb.client import (
    BASE_URL,
    TMDBAuthError,
    TMDBClient,
    TMDBNotFound,
    TMDBUnavailable,
    create_http_client,
)
from tests.helpers import FakeClock


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
async def tmdb(sleeps):
    async def fake_sleep(seconds):
        sleeps.append(seconds)

    http = create_http_client("tok-secreto")
    yield TMDBClient(http, TTLCache(clock=FakeClock()), sleep=fake_sleep)
    await http.aclose()


@pytest.fixture
def mock():
    with respx.mock(base_url=BASE_URL) as m:
        yield m


async def test_sends_bearer_token(tmdb, mock):
    route = mock.get("/genre/tv/list").respond(json={"genres": []})
    await tmdb.get("/genre/tv/list", ttl=60)
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-secreto"


async def test_second_identical_call_uses_cache(tmdb, mock):
    route = mock.get("/x").respond(json={"ok": 1})
    await tmdb.get("/x", {"a": "1", "b": "2"}, ttl=60)
    assert await tmdb.get("/x", {"b": "2", "a": "1"}, ttl=60) == {"ok": 1}
    assert route.call_count == 1


async def test_errors_are_not_cached(tmdb, mock):
    route = mock.get("/x").mock(side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": 1})])
    with pytest.raises(TMDBUnavailable):
        await tmdb.get("/x", ttl=60)
    assert await tmdb.get("/x", ttl=60) == {"ok": 1} and route.call_count == 2


@pytest.mark.parametrize(
    "header, expected",
    [({"Retry-After": "1"}, 1.0), ({"Retry-After": "5"}, 2.0), ({}, 1.0), ({"Retry-After": "abc"}, 1.0)],
)
async def test_429_retries_once_after_retry_after(tmdb, mock, sleeps, header, expected):
    mock.get("/x").mock(side_effect=[httpx.Response(429, headers=header), httpx.Response(200, json={"ok": 1})])
    assert await tmdb.get("/x", ttl=60) == {"ok": 1}
    assert sleeps == [expected]


async def test_429_twice_raises_unavailable(tmdb, mock):
    mock.get("/x").mock(side_effect=[httpx.Response(429), httpx.Response(429)])
    with pytest.raises(TMDBUnavailable):
        await tmdb.get("/x", ttl=60)


@pytest.mark.parametrize(
    "effect, exc",
    [
        (httpx.Response(401), TMDBAuthError),
        (httpx.Response(404), TMDBNotFound),
        (httpx.Response(503), TMDBUnavailable),
        (httpx.ReadTimeout("t"), TMDBUnavailable),
        (httpx.ConnectError("c"), TMDBUnavailable),
    ],
)
async def test_maps_failures_to_exceptions(tmdb, mock, effect, exc):
    mock.get("/x").mock(side_effect=[effect])
    with pytest.raises(exc):
        await tmdb.get("/x", ttl=60)


async def test_token_never_logged(tmdb, mock, caplog):
    caplog.set_level(logging.DEBUG)
    mock.get("/x").respond(401)
    with pytest.raises(TMDBAuthError):
        await tmdb.get("/x", ttl=60)
    assert "tok-secreto" not in caplog.text
