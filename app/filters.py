"""Tradução da URL do catálogo em `Filters` e de `Filters` em parâmetros do /discover/tv."""

from collections.abc import Mapping, Sequence
from datetime import date

from app.models import ALL_TYPES, Filters

SORTS = {
    "popularidade": "popularity.desc",
    "nota": "vote_average.desc",
    "recentes": "first_air_date.desc",
    "nome": "name.asc",
}
RATINGS = (5, 6, 7, 8)
MAX_PAGE = 500
MIN_VOTES = 50
MIN_YEAR = 1900


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _first(values: Sequence[str]) -> str | None:
    return values[0] if values else None


def _ids(values: Sequence[str]) -> tuple[int, ...]:
    ids = (_to_int(v) for v in values)
    return tuple(dict.fromkeys(i for i in ids if i is not None and i > 0))


def _year(values: Sequence[str], current_year: int) -> int | None:
    year = _to_int(_first(values) or "")
    if year is None or not MIN_YEAR <= year <= current_year + 1:
        return None
    return year


def parse_page(values: Sequence[str]) -> int:
    page = _to_int(_first(values) or "")
    if page is None or not 1 <= page <= MAX_PAGE:
        return 1
    return page


def parse_filters(query: Mapping[str, Sequence[str]], current_year: int) -> Filters:
    chosen_types = set(query.get("tipos", ()))
    types = tuple(t for t in ALL_TYPES if t in chosen_types) or ALL_TYPES

    year_from = _year(query.get("ano_de", ()), current_year)
    year_to = _year(query.get("ano_ate", ()), current_year)
    if year_from is not None and year_to is not None and year_from > year_to:
        year_from, year_to = year_to, year_from

    rating = _to_int(_first(query.get("nota", ())) or "")
    sort = _first(query.get("ordem", ()))

    return Filters(
        providers=_ids(query.get("servicos", ())),
        types=types,
        genres=_ids(query.get("generos", ())),
        year_from=year_from,
        year_to=year_to,
        min_rating=rating if rating in RATINGS else None,
        sort=sort if sort in SORTS else "popularidade",
        page=parse_page(query.get("pagina", ())),
    )


def discover_params(filters: Filters, region: str, language: str, today: date) -> dict[str, str]:
    params = {
        "watch_region": region,
        "language": language,
        "with_watch_monetization_types": "|".join(filters.types),
        "sort_by": SORTS[filters.sort],
        "page": str(filters.page),
    }
    if filters.providers:
        params["with_watch_providers"] = "|".join(map(str, filters.providers))
    if filters.genres:
        params["with_genres"] = "|".join(map(str, filters.genres))
    if filters.year_from is not None:
        params["first_air_date.gte"] = f"{filters.year_from}-01-01"

    latest = date(filters.year_to, 12, 31) if filters.year_to is not None else None
    if filters.sort == "recentes":
        latest = min(latest, today) if latest else today
    if latest is not None:
        params["first_air_date.lte"] = latest.isoformat()

    if filters.min_rating is not None:
        params["vote_average.gte"] = str(filters.min_rating)
    if filters.min_rating is not None or filters.sort == "nota":
        params["vote_count.gte"] = str(MIN_VOTES)
    return params
