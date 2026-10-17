import json

import httpx
import pytest
import respx

from app.models import Marks, TrackedSeries
from app.tracking.service import InvalidAction
from app.tracking.store import TrackingUnavailable
from app.tracking.supabase_repository import SupabaseTrackingRepository

URL = "https://proj.supabase.co"


@pytest.fixture
async def repo():
    async with httpx.AsyncClient(timeout=10) as http:
        yield SupabaseTrackingRepository(http, URL, "pk", "tok")


@pytest.fixture
def mock():
    with respx.mock(base_url=f"{URL}/rest/v1") as m:
        yield m


def sent(route):
    request = route.calls.last.request
    return request, (json.loads(request.content) if request.content else None)


async def test_every_request_carries_the_person_token(repo, mock):
    route = mock.get("/watched_episodes").respond(json=[])
    await repo.watched(7)
    request, _ = sent(route)
    assert request.headers["apikey"] == "pk" and request.headers["authorization"] == "Bearer tok"


async def test_marks_for(repo, mock):
    route = mock.get("/series_tracking").respond(json=[{"tmdb_id": 1, "status": "watching", "favorite": True}])
    assert await repo.marks_for([1, 2]) == {1: Marks("watching", True)}
    params = route.calls.last.request.url.params
    assert params["select"] == "tmdb_id,status,favorite" and params["tmdb_id"] == "in.(1,2)"


async def test_marks_for_empty_makes_no_request(repo, mock):
    route = mock.get("/series_tracking").respond(json=[])
    assert await repo.marks_for([]) == {} and not route.called
    assert await repo.marks(3) == Marks()


async def test_watched(repo, mock):
    route = mock.get("/watched_episodes").respond(json=[{"season": 1, "episode": 2}, {"season": 0, "episode": 1}])
    assert await repo.watched(7) == frozenset({(1, 2), (0, 1)})
    params = route.calls.last.request.url.params
    assert params["select"] == "season,episode" and params["tmdb_id"] == "eq.7"


async def test_save_sends_one_rpc_with_everything(repo, mock):
    route = mock.post("/rpc/save_tracking").respond(204)
    await repo.save(7, name="X", poster_path="/p.jpg", status="watching", favorite=True,
                    add=[(1, 1), (1, 2)], remove=[(0, 1)], runtimes={(1, 1): 50})
    assert sent(route)[1] == {
        "p_tmdb_id": 7, "p_name": "X", "p_poster_path": "/p.jpg", "p_status": "watching", "p_favorite": True,
        "p_add": [{"season": 1, "episode": 1, "runtime": 50}, {"season": 1, "episode": 2, "runtime": None}],
        "p_remove": [{"season": 0, "episode": 1}]}


async def test_save_with_invalid_status_is_invalid_action(repo, mock):
    mock.post("/rpc/save_tracking").respond(400, json={"code": "23514", "message": "check constraint"})
    with pytest.raises(InvalidAction):
        await repo.save(7, name="X", poster_path=None, status="xyz", favorite=False)


@pytest.mark.parametrize(("fn", "payload", "expected"), [
    ("tracking_counts", {"watching": 2, "want": 1, "watched": 0, "favorite": 3},
     {"watching": 2, "want": 1, "watched": 0, "favorite": 3}),
    ("watch_time", {"episodes": 5, "minutes": 250}, (5, 250)),
    ("missing_runtimes", [{"tmdb_id": 1, "season": 2}, {"tmdb_id": 1, "season": 3}, {"tmdb_id": 9, "season": 1}],
     {1: {2, 3}, 9: {1}}),
])
async def test_aggregate_functions(repo, mock, fn, payload, expected):
    route = mock.post(f"/rpc/{fn}").respond(json=payload)
    method = {"tracking_counts": repo.counts, "watch_time": repo.watch_time, "missing_runtimes": repo.missing_runtimes}[fn]
    assert await method() == expected
    assert sent(route)[1] == {}


async def test_set_runtimes(repo, mock):
    route = mock.post("/rpc/set_runtimes").respond(204)
    await repo.set_runtimes(7, {(1, 1): 50})
    assert sent(route)[1] == {"p_tmdb_id": 7, "p_runtimes": [{"season": 1, "episode": 1, "runtime": 50}]}


@pytest.mark.parametrize(("tab", "param", "value"), [("watching", "status", "eq.watching"), ("favorite", "favorite", "is.true")])
async def test_list_tab(repo, mock, tab, param, value):
    route = mock.get("/series_tracking").respond(json=[
        {"tmdb_id": 1, "name": "A", "poster_path": "/a.jpg", "status": "watching", "favorite": True}])
    assert await repo.list_tab(tab) == [
        TrackedSeries(1, "A", "https://image.tmdb.org/t/p/w342/a.jpg", Marks("watching", True))]
    params = route.calls.last.request.url.params
    assert params[param] == value and params["order"] == "updated_at.desc"
    assert params["select"] == "tmdb_id,name,poster_path,status,favorite"


@pytest.mark.parametrize("response", [httpx.ConnectError("fora"), httpx.Response(503), httpx.Response(401, json={})])
async def test_failures_are_tracking_unavailable(repo, mock, response):
    route = mock.get("/watched_episodes")
    route.mock(side_effect=response) if isinstance(response, Exception) else route.mock(return_value=response)
    with pytest.raises(TrackingUnavailable):
        await repo.watched(7)
