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


def parse_page(values: Sequence[str]) -> int:
    page = _to_int(_first(values) or "")
    if page is None or not 1 <= page <= MAX_PAGE:
        return 1
    return page


def parse_filters(query: Mapping[str, Sequence[str]]) -> Filters:
    rating = _to_int(_first(query.get("nota", ())) or "")
    sort = _first(query.get("ordem", ()))
    return Filters(
        providers=_ids(query.get("servicos", ())),
        genres=_ids(query.get("generos", ())),
        min_rating=rating if rating in RATINGS else None,
        sort=sort if sort in SORTS else "popularidade",
        page=parse_page(query.get("pagina", ())),
    )


def discover_params(filters: Filters, region: str, language: str, today: date) -> dict[str, str]:
    """Sempre envia todos os tipos de disponibilidade: é isso que garante "disponível em streaming"."""
    params = {
        "watch_region": region,
        "language": language,
        "with_watch_monetization_types": "|".join(ALL_TYPES),
        "sort_by": SORTS[filters.sort],
        "page": str(filters.page),
    }
    if filters.providers:
        params["with_watch_providers"] = "|".join(map(str, filters.providers))
    if filters.genres:
        params["with_genres"] = "|".join(map(str, filters.genres))
    if filters.sort == "recentes":
        params["first_air_date.lte"] = today.isoformat()
    if filters.min_rating is not None:
        params["vote_average.gte"] = str(filters.min_rating)
    if filters.min_rating is not None or filters.sort == "nota":
        params["vote_count.gte"] = str(MIN_VOTES)
    return params
