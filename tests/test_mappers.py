from datetime import date

import pytest

from app.mappers import (
    card_providers,
    image_url,
    pick_trailer,
    to_card,
    to_catalog_page,
    to_detail,
    to_provider_list,
    to_season_detail,
    to_watch_options,
    watch_services,
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


def test_provider_list_one_logo_per_service():
    names = ["Netflix", "Paramount+ Amazon Channel", "Paramount Plus", "Netflix Standard with Ads", "Plex Channel", "Plex"]
    data = {"results": [{"provider_id": i, "provider_name": n, "display_priority": i} for i, n in enumerate(names)]}
    merged = to_provider_list(data, "BR")
    assert [p.name for p in merged] == ["Netflix", "Paramount Plus", "Plex"]
    # cada logo carrega os ids de todas as versões do serviço, o principal primeiro
    assert [p.ids for p in merged] == [(0, 3), (2, 1), (5, 4)]


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



def named(i, name, prio=0):
    return {"provider_id": i, "provider_name": name, "logo_path": f"/{i}.png", "display_priority": prio}


def test_watch_options_merge_variants_into_main_service():
    w = to_watch_options({"flatrate": [
        named(582, "Paramount+ Amazon Channel", 1), named(531, "Paramount Plus", 2),
        named(1853, "Paramount Plus Apple TV channel", 3), named(2303, "Paramount Plus Premium", 4),
        named(8, "Netflix", 5), named(1796, "Netflix Standard with Ads", 6)]})
    assert [x.id for x in w.by_type["flatrate"]] == [531, 8]


def test_variant_is_kept_when_main_service_is_absent():
    w = to_watch_options({"flatrate": [named(1825, "HBO Max Amazon Channel"),
                                       named(2141, "MGM Plus Amazon Channel", 1),
                                       named(2142, "MGM+ Apple TV Channel", 2)]})
    assert [x.id for x in w.by_type["flatrate"]] == [1825, 2141]


def test_card_providers_merge_variants_across_types_but_not_different_services():
    d = {"flatrate": [named(119, "Amazon Prime Video")], "ads": [named(2100, "Amazon Prime Video with Ads")],
         "rent": [named(10, "Amazon Video")], "buy": [named(2243, "Apple TV Amazon Channel"), named(350, "Apple TV", 1)]}
    assert [x.id for x in card_providers(d)] == [119, 10, 350]


def test_watch_services_one_logo_per_service_with_how_to_watch():
    w = to_watch_options({"flatrate": [named(8, "Netflix"), named(531, "Paramount Plus", 1)],
                          "free": [named(10, "Amazon Video")],
                          "ads": [named(1796, "Netflix Standard with Ads")],
                          "rent": [named(10, "Amazon Video")], "buy": [named(10, "Amazon Video")]})
    assert [(x.id, how) for x, how in watch_services(w)] == [
        (8, "assinatura ou com anúncios"), (531, "assinatura"), (10, "grátis, aluguel ou compra")]
    assert watch_services(WatchOptions(None, {})) == ()

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


def test_to_season_detail_from_fixture():
    s = to_season_detail(load_fixture("season_100088_1.json"), series_id=100088)
    assert (s.series_id, s.number, len(s.episodes)) == (100088, 1, 9)
    first = s.episodes[0]
    assert (first.season, first.number, first.air_date) == (1, 1, date(2023, 1, 15))
    assert first.still_url.startswith("https://image.tmdb.org/t/p/w300/")


def test_to_season_detail_tolerates_missing_fields():
    s = to_season_detail({"season_number": 0, "name": "Especiais", "episodes": [
        {"episode_number": 2, "name": "B", "air_date": "", "still_path": None},
        {"episode_number": 1, "name": "A"}]}, series_id=5)
    assert [e.number for e in s.episodes] == [1, 2]
    second = s.episodes[1]
    assert (second.air_date, second.still_url, second.runtime, second.overview) == (None, None, None, "")


def test_detail_reads_last_aired_and_poster_path():
    data = load_fixture("tv_100088.json")
    d = to_detail(data, "BR")
    assert d.last_aired == (2, 7) and d.poster_path == data["poster_path"]


def test_last_aired_is_none_without_last_episode():
    data = load_fixture("tv_100088.json")
    data["last_episode_to_air"] = None
    assert to_detail(data, "BR").last_aired is None


def test_last_aired_when_last_episode_is_a_special():
    data = load_fixture("tv_100088.json")
    data["last_episode_to_air"] = {"season_number": 0, "episode_number": 3, "air_date": "2024-12-25"}
    data["seasons"] = [{"season_number": 1, "episode_count": 9, "air_date": "2023-01-15", "name": "T1"},
                       {"season_number": 2, "episode_count": 7, "air_date": "2025-04-13", "name": "T2"}]
    assert to_detail(data, "BR").last_aired == (1, 9)


@pytest.mark.parametrize(("next_episode", "expected"), [
    ({"season_number": 2, "episode_number": 3}, (2, 2)),
    ({"season_number": 2, "episode_number": 1}, (1, 9)),
])
def test_last_aired_when_a_special_airs_mid_season(next_episode, expected):
    data = load_fixture("tv_100088.json")
    data["last_episode_to_air"] = {"season_number": 0, "episode_number": 4, "air_date": "2026-10-10"}
    data["next_episode_to_air"] = next_episode
    data["seasons"] = [{"season_number": 1, "episode_count": 9, "air_date": "2023-01-15", "name": "T1"},
                       {"season_number": 2, "episode_count": 10, "air_date": "2026-10-01", "name": "T2"}]
    assert to_detail(data, "BR").last_aired == expected


@pytest.mark.parametrize(("extra", "expected"), [
    ({"episode_run_time": [42, 58]}, 50),
    ({"episode_run_time": [], "last_episode_to_air": {"season_number": 2, "episode_number": 7, "runtime": 61}}, 61),
    ({"episode_run_time": [], "last_episode_to_air": None}, None),
])
def test_typical_runtime(extra, expected):
    data = load_fixture("tv_100088.json") | extra
    assert to_detail(data, "BR").typical_runtime == expected
