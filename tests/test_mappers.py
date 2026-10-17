import pytest

from app.mappers import (
    card_providers,
    image_url,
    pick_trailer,
    to_card,
    to_catalog_page,
    to_detail,
    to_provider_list,
    to_watch_options,
    years_label,
)
from app.models import SeriesCard, WatchOptions
from tests.helpers import load_fixture


def test_image_url():
    assert image_url(None, "w342") is None
    assert image_url("/a.jpg", "w342") == "https://image.tmdb.org/t/p/w342/a.jpg"


def test_to_card_full_and_empty():
    c = to_card({"id": 1, "name": "X", "first_air_date": "2023-01-15", "vote_average": 8.64, "vote_count": 10,
                 "poster_path": "/p.jpg"})
    assert c == SeriesCard(1, "X", 2023, 8.64, "https://image.tmdb.org/t/p/w342/p.jpg", None)
    e = to_card({"id": 2, "name": "Y", "first_air_date": "", "vote_average": 0, "vote_count": 0, "poster_path": None})
    assert (e.year, e.rating, e.poster_url) == (None, None, None)


def test_total_pages_capped_at_500():
    assert to_catalog_page({"page": 1, "total_pages": 800, "total_results": 16000, "results": []}).total_pages == 500


def test_parses_real_discover_and_search_fixtures():
    for name in ("discover.json", "search_office.json"):
        data = load_fixture(name)
        assert [c.id for c in to_catalog_page(data).items] == [r["id"] for r in data["results"]]


def test_provider_list_sorted_by_region_priority():
    data = {"results": [
        {"provider_id": 1, "provider_name": "A", "logo_path": "/a.png", "display_priority": 0,
         "display_priorities": {"BR": 5}},
        {"provider_id": 2, "provider_name": "B", "logo_path": "/b.png", "display_priority": 9,
         "display_priorities": {"BR": 1}},
        {"provider_id": 3, "provider_name": "C", "logo_path": None, "display_priority": 3,
         "display_priorities": {}},
    ]}
    assert [p.id for p in to_provider_list(data, "BR")] == [2, 3, 1]


def p(i, prio=0):
    return {"provider_id": i, "provider_name": f"P{i}", "logo_path": f"/{i}.png", "display_priority": prio}


def test_watch_options_grouped_in_type_order():
    w = to_watch_options({"link": "L", "buy": [p(3, 2), p(2, 1)], "flatrate": [p(1)]})
    assert w.link == "L" and list(w.by_type) == ["flatrate", "buy"]
    assert [x.id for x in w.by_type["buy"]] == [2, 3]
    assert to_watch_options(None) == WatchOptions(None, {})


def test_card_providers_unique_limited_to_4():
    d = {"flatrate": [p(1)], "ads": [p(1), p(2)], "rent": [p(3)], "buy": [p(4), p(5)]}
    assert [x.id for x in card_providers(d)] == [1, 2, 3, 4]
    assert card_providers(None) == ()


def v(key, lang, type_="Trailer", site="YouTube"):
    return {"key": key, "iso_639_1": lang, "type": type_, "site": site}


def test_pick_trailer_priority():
    assert pick_trailer([v("en", "en"), v("ptT", "pt", "Teaser"), v("pt", "pt"), v("vim", "pt", site="Vimeo")]) == "pt"
    assert pick_trailer([v("t1", "en", "Teaser"), v("t2", "pt", "Teaser")]) == "t2"
    assert pick_trailer([v("x", "fr")]) == "x"
    assert pick_trailer([]) is None


@pytest.mark.parametrize("args, label", [((2023, 2025, True), "2023–"), ((2013, 2019, False), "2013–2019"),
                                         ((2019, 2019, False), "2019"), ((None, None, False), "")])
def test_years_label(args, label):
    assert years_label(*args) == label


def test_to_detail_from_real_fixture():
    data = load_fixture("tv_100088.json")
    d = to_detail(data, "BR")
    assert d.id == 100088 and len(d.cast) <= 10
    assert d.cast[0].character == data["aggregate_credits"]["cast"][0]["roles"][0]["character"]
    assert d.watch == to_watch_options(data["watch/providers"]["results"].get("BR"))


def test_to_detail_rules():
    data = load_fixture("tv_100088.json")
    data.update(status="Returning Series", overview="", seasons=[
        {"season_number": 0, "name": "Especiais", "air_date": None, "episode_count": 1, "poster_path": None},
        {"season_number": 1, "name": "Temporada 1", "air_date": "2023-01-15", "episode_count": 9, "poster_path": None}])
    d = to_detail(data, "BR", overview_fallback="English")
    assert d.status_label == "Em exibição" and d.overview == "English"
    assert [s.number for s in d.seasons] == [1, 0]
    data["status"] = "Algo Novo"
    assert to_detail(data, "BR").status_label == "Algo Novo"


# Review Focus 2
def test_to_detail_tolerates_missing_optional_fields():
    d = to_detail({"id": 1, "name": "X"}, "BR")
    assert (d.poster_url, d.backdrop_url, d.trailer_youtube_key) == (None, None, None)
    assert (d.cast, d.seasons, d.genres, d.years_label) == ((), (), (), "")
    assert d.watch == WatchOptions(None, {})


# Revisão final #5: spec §8.4 — "2023–" se ainda está em exibição OU produção
@pytest.mark.parametrize("status", ["Returning Series", "In Production", "Planned", "Pilot"])
def test_years_label_is_open_when_status_is_ongoing(status):
    data = {"id": 1, "name": "X", "first_air_date": "2019-01-01", "last_air_date": "2024-05-01",
            "in_production": False, "status": status}
    assert to_detail(data, "BR").years_label == "2019–"


def test_years_label_closed_when_ended():
    data = {"id": 1, "name": "X", "first_air_date": "2019-01-01", "last_air_date": "2024-05-01",
            "in_production": False, "status": "Ended"}
    assert to_detail(data, "BR").years_label == "2019–2024"
