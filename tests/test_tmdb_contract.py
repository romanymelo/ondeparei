"""Confirma, contra a API real, as suposições da spec §12. Roda só com `uv run pytest -m tmdb`."""

import httpx
import pytest

from app.config import load_settings
from app.tmdb.client import BASE_URL

pytestmark = pytest.mark.tmdb


@pytest.fixture(scope="module")
def api():
    token = load_settings().tmdb_token.get_secret_value()
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10) as client:
        yield client


def test_append_watch_providers_on_tv_details(api):
    r = api.get("/tv/100088", params={"language": "pt-BR",
                                      "append_to_response": "aggregate_credits,videos,watch/providers",
                                      "include_video_language": "pt,en,null"})
    assert r.status_code == 200
    d = r.json()
    assert "results" in d["watch/providers"]
    assert "cast" in d["aggregate_credits"] and "results" in d["videos"]


def test_provider_list_has_display_priorities(api):
    r = api.get("/watch/providers/tv", params={"watch_region": "BR"})
    assert "BR" in r.json()["results"][0]["display_priorities"]


def test_discover_beyond_page_500_is_rejected(api):
    r = api.get("/discover/tv", params={"page": 501, "watch_region": "BR",
                                        "with_watch_monetization_types": "flatrate"})
    assert r.status_code != 200 or r.json()["results"] == []


def test_trending_tv_day_has_spotlight_fields(api):
    r = api.get("/trending/tv/day", params={"language": "pt-BR"})
    assert r.status_code == 200
    item = r.json()["results"][0]
    assert {"id", "name", "backdrop_path", "overview", "genre_ids", "first_air_date", "vote_average"} <= item.keys()
