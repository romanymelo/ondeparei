from datetime import date

import pytest

from app.filters import discover_params, parse_filters, parse_page
from app.models import Filters


def test_empty_query_gives_defaults():
    assert parse_filters({}) == Filters()


def test_parses_all_fields():
    q = {"servicos": ["8", "1899"], "generos": ["18"], "nota": ["7"], "ordem": ["nota"], "pagina": ["3"]}
    assert parse_filters(q) == Filters(providers=(8, 1899), genres=(18,), min_rating=7, sort="nota", page=3)


def test_invalid_values_fall_back_to_defaults():
    q = {"servicos": ["abc", "8", "8"], "generos": ["-1", "x"], "nota": ["9"], "ordem": ["aleatorio"],
         "pagina": ["501"]}
    assert parse_filters(q) == Filters(providers=(8,))


def test_removed_filters_are_ignored():
    q = {"tipos": ["rent"], "ano_de": ["2015"], "ano_ate": ["2020"]}
    assert parse_filters(q) == Filters()


@pytest.mark.parametrize("raw", [["0"], ["-1"], ["x"], []])
def test_bad_page_is_1(raw):
    assert parse_page(raw) == 1


def test_active_count():
    assert Filters().active_count == 0
    assert Filters(providers=(8,), min_rating=7).active_count == 2
    assert Filters(genres=(18, 35)).active_count == 1


TODAY = date(2026, 10, 16)


def test_default_discover_params():
    assert discover_params(Filters(), "BR", "pt-BR", TODAY) == {
        "watch_region": "BR", "language": "pt-BR",
        "with_watch_monetization_types": "flatrate|free|ads|rent|buy", "sort_by": "popularity.desc", "page": "1"}


def test_full_discover_params():
    p = discover_params(Filters(providers=(8, 1899), genres=(18, 35), min_rating=7), "BR", "pt-BR", TODAY)
    assert p["with_watch_providers"] == "8|1899" and p["with_genres"] == "18|35"
    assert p["vote_average.gte"] == "7" and p["vote_count.gte"] == "50"
    assert p["with_watch_monetization_types"] == "flatrate|free|ads|rent|buy"
    assert "first_air_date.gte" not in p and "first_air_date.lte" not in p


def test_sort_by_rating_requires_min_votes():
    p = discover_params(Filters(sort="nota"), "BR", "pt-BR", TODAY)
    assert p["sort_by"] == "vote_average.desc" and p["vote_count.gte"] == "50"


def test_recent_sort_excludes_future():
    p = discover_params(Filters(sort="recentes"), "BR", "pt-BR", TODAY)
    assert p["sort_by"] == "first_air_date.desc" and p["first_air_date.lte"] == "2026-10-16"


def test_name_sort():
    assert discover_params(Filters(sort="nome"), "BR", "pt-BR", TODAY)["sort_by"] == "name.asc"
