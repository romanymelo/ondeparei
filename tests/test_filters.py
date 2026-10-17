from datetime import date

import pytest

from app.filters import discover_params, parse_filters, parse_page
from app.models import Filters


def test_empty_query_gives_defaults():
    assert parse_filters({}, 2026) == Filters()


def test_parses_all_fields():
    q = {"servicos": ["8", "1899"], "tipos": ["flatrate"], "generos": ["18"], "ano_de": ["2015"],
         "ano_ate": ["2020"], "nota": ["7"], "ordem": ["nota"], "pagina": ["3"]}
    assert parse_filters(q, 2026) == Filters(providers=(8, 1899), types=("flatrate",), genres=(18,),
                                             year_from=2015, year_to=2020, min_rating=7, sort="nota", page=3)


def test_invalid_values_fall_back_to_defaults():
    q = {"servicos": ["abc", "8", "8"], "tipos": ["xyz"], "ano_de": ["1800"], "ano_ate": ["2028"],
         "nota": ["9"], "ordem": ["aleatorio"], "pagina": ["501"]}
    assert parse_filters(q, 2026) == Filters(providers=(8,))


@pytest.mark.parametrize("raw", [["0"], ["-1"], ["x"], []])
def test_bad_page_is_1(raw):
    assert parse_page(raw) == 1


def test_year_upper_bound_is_next_year():
    assert parse_filters({"ano_ate": ["2027"]}, 2026).year_to == 2027


def test_swaps_reversed_years():
    f = parse_filters({"ano_de": ["2020"], "ano_ate": ["2015"]}, 2026)
    assert (f.year_from, f.year_to) == (2015, 2020)


def test_active_count():
    assert Filters().active_count == 0
    assert Filters(providers=(8,), min_rating=7).active_count == 2
    assert Filters(types=("flatrate",), year_to=2020).active_count == 2


TODAY = date(2026, 10, 16)


def test_default_discover_params():
    assert discover_params(Filters(), "BR", "pt-BR", TODAY) == {
        "watch_region": "BR", "language": "pt-BR",
        "with_watch_monetization_types": "flatrate|free|ads|rent|buy", "sort_by": "popularity.desc", "page": "1"}


def test_full_discover_params():
    p = discover_params(Filters(providers=(8, 1899), genres=(18, 35), year_from=2015, year_to=2020, min_rating=7),
                        "BR", "pt-BR", TODAY)
    assert p["with_watch_providers"] == "8|1899" and p["with_genres"] == "18|35"
    assert p["first_air_date.gte"] == "2015-01-01" and p["first_air_date.lte"] == "2020-12-31"
    assert p["vote_average.gte"] == "7" and p["vote_count.gte"] == "50"


def test_sort_by_rating_requires_min_votes():
    p = discover_params(Filters(sort="nota"), "BR", "pt-BR", TODAY)
    assert p["sort_by"] == "vote_average.desc" and p["vote_count.gte"] == "50"


def test_recent_sort_excludes_future():
    p = discover_params(Filters(sort="recentes"), "BR", "pt-BR", TODAY)
    assert p["sort_by"] == "first_air_date.desc" and p["first_air_date.lte"] == "2026-10-16"


# Review Focus 1
@pytest.mark.parametrize("year_to, expected", [(2020, "2020-12-31"), (2027, "2026-10-16")])
def test_recent_sort_with_year_to_uses_earlier_date(year_to, expected):
    p = discover_params(Filters(sort="recentes", year_to=year_to), "BR", "pt-BR", TODAY)
    assert p["first_air_date.lte"] == expected


def test_name_sort():
    assert discover_params(Filters(sort="nome"), "BR", "pt-BR", TODAY)["sort_by"] == "name.asc"
