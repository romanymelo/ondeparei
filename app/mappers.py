"""Conversão das respostas JSON da TMDB nos modelos do domínio."""

from collections.abc import Mapping, Sequence

from app.filters import MAX_PAGE
from app.models import (
    ALL_TYPES,
    CastMember,
    CatalogPage,
    Genre,
    Provider,
    Season,
    SeriesCard,
    SeriesDetail,
    WatchOptions,
)

IMAGE_BASE = "https://image.tmdb.org/t/p"
WATCH_TYPE_LABELS = {
    "flatrate": "Assinatura",
    "free": "Grátis",
    "ads": "Com anúncios",
    "rent": "Aluguel",
    "buy": "Compra",
}
STATUS_LABELS = {
    "Returning Series": "Em exibição",
    "Ended": "Encerrada",
    "Canceled": "Cancelada",
    "In Production": "Em produção",
    "Planned": "Planejada",
    "Pilot": "Piloto",
}
ONGOING_STATUSES = {"Returning Series", "In Production", "Planned", "Pilot"}
MAX_CAST = 10


def image_url(path: str | None, size: str) -> str | None:
    return f"{IMAGE_BASE}/{size}{path}" if path else None


def _year(date_str: str | None) -> int | None:
    if date_str and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def _rating(item: Mapping) -> float | None:
    return item.get("vote_average") if item.get("vote_count") else None


def _provider(item: Mapping) -> Provider:
    return Provider(item["provider_id"], item["provider_name"], image_url(item.get("logo_path"), "w92"))


def _by_priority(items: Sequence[Mapping]) -> list[Mapping]:
    return sorted(items, key=lambda i: i.get("display_priority", 0))


def to_card(item: Mapping) -> SeriesCard:
    return SeriesCard(
        id=item["id"],
        name=item.get("name", ""),
        year=_year(item.get("first_air_date")),
        rating=_rating(item),
        poster_url=image_url(item.get("poster_path"), "w342"),
    )


def to_catalog_page(data: Mapping) -> CatalogPage:
    return CatalogPage(
        items=tuple(to_card(item) for item in data.get("results", [])),
        page=data.get("page", 1),
        total_pages=min(data.get("total_pages", 0), MAX_PAGE),
        total_results=data.get("total_results", 0),
    )


def to_provider_list(data: Mapping, region: str) -> tuple[Provider, ...]:
    items = sorted(
        data.get("results", []),
        key=lambda i: i.get("display_priorities", {}).get(region, i.get("display_priority", 0)),
    )
    return tuple(_provider(item) for item in items)


def to_genres(data: Mapping) -> tuple[Genre, ...]:
    return tuple(Genre(g["id"], g["name"]) for g in data.get("genres", []))


def to_watch_options(region_data: Mapping | None) -> WatchOptions:
    if not region_data:
        return WatchOptions(None, {})
    by_type = {
        kind: tuple(_provider(item) for item in _by_priority(region_data[kind]))
        for kind in ALL_TYPES
        if region_data.get(kind)
    }
    return WatchOptions(region_data.get("link"), by_type)


def card_providers(region_data: Mapping | None, limit: int = 4) -> tuple[Provider, ...]:
    unique: dict[int, Provider] = {}
    for providers in to_watch_options(region_data).by_type.values():
        for provider in providers:
            unique.setdefault(provider.id, provider)
    return tuple(unique.values())[:limit]


def pick_trailer(videos: Sequence[Mapping]) -> str | None:
    youtube = [v for v in videos if v.get("site") == "YouTube"]
    for kind in ("Trailer", "Teaser"):
        of_kind = [v for v in youtube if v.get("type") == kind]
        for language in ("pt", "en"):
            for video in of_kind:
                if video.get("iso_639_1") == language:
                    return video["key"]
        if of_kind:
            return of_kind[0]["key"]
    return None


def years_label(first: int | None, last: int | None, in_production: bool) -> str:
    if first is None:
        return ""
    if in_production:
        return f"{first}–"
    if last is None or last == first:
        return str(first)
    return f"{first}–{last}"


def _season(item: Mapping) -> Season:
    return Season(
        number=item.get("season_number", 0),
        name=item.get("name", ""),
        year=_year(item.get("air_date")),
        episode_count=item.get("episode_count") or 0,
        poster_url=image_url(item.get("poster_path"), "w185"),
    )


def _cast_member(item: Mapping) -> CastMember:
    roles = item.get("roles") or []
    character = roles[0].get("character", "") if roles else item.get("character", "")
    return CastMember(item.get("name", ""), character, image_url(item.get("profile_path"), "w185"))


def to_detail(data: Mapping, region: str, overview_fallback: str = "") -> SeriesDetail:
    first_year = _year(data.get("first_air_date"))
    last_year = _year(data.get("last_air_date"))
    in_production = bool(data.get("in_production"))
    status = data.get("status") or ""
    seasons = sorted((_season(s) for s in data.get("seasons") or []), key=lambda s: (s.number == 0, s.number))
    cast = (data.get("aggregate_credits") or {}).get("cast") or []
    region_watch = ((data.get("watch/providers") or {}).get("results") or {}).get(region)

    return SeriesDetail(
        id=data["id"],
        name=data.get("name", ""),
        original_name=data.get("original_name") or data.get("name", ""),
        overview=data.get("overview") or overview_fallback,
        first_year=first_year,
        last_year=last_year,
        years_label=years_label(first_year, last_year, in_production or status in ONGOING_STATUSES),
        status_label=STATUS_LABELS.get(status, status),
        in_production=in_production,
        seasons_count=data.get("number_of_seasons") or 0,
        episodes_count=data.get("number_of_episodes") or 0,
        genres=tuple(g["name"] for g in data.get("genres") or []),
        rating=_rating(data),
        vote_count=data.get("vote_count") or 0,
        poster_url=image_url(data.get("poster_path"), "w500"),
        backdrop_url=image_url(data.get("backdrop_path"), "w1280"),
        trailer_youtube_key=pick_trailer((data.get("videos") or {}).get("results") or []),
        seasons=tuple(seasons),
        cast=tuple(_cast_member(c) for c in cast[:MAX_CAST]),
        watch=to_watch_options(region_watch),
    )
