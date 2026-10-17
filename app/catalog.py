"""Serviço do catálogo: orquestra as chamadas à TMDB e devolve modelos do domínio."""

import asyncio
import dataclasses
from collections.abc import Callable
from datetime import date

from app.filters import discover_params
from app.mappers import card_providers, to_catalog_page, to_detail, to_genres, to_provider_list
from app.models import CatalogPage, Filters, Genre, Provider, SeriesCard, SeriesDetail
from app.tmdb.client import TMDBClient, TMDBError

TTL_LISTS = 24 * 3600
TTL_DETAIL = 6 * 3600
TTL_RESULTS = 3600
SEARCH_CONCURRENCY = 10
MAX_QUERY = 100
DETAIL_APPEND = "aggregate_credits,videos,watch/providers"
VIDEO_LANGUAGES = "pt,en,null"
FALLBACK_LANGUAGE = "en-US"


class Catalog:
    def __init__(
        self,
        client: TMDBClient,
        region: str,
        language: str,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._client = client
        self._region = region
        self._language = language
        self._today = today

    async def discover(self, filters: Filters) -> CatalogPage:
        params = discover_params(filters, self._region, self._language, self._today())
        return to_catalog_page(await self._client.get("/discover/tv", params, ttl=TTL_RESULTS))

    async def providers(self) -> tuple[Provider, ...]:
        params = {"watch_region": self._region, "language": self._language}
        data = await self._client.get("/watch/providers/tv", params, ttl=TTL_LISTS)
        return to_provider_list(data, self._region)

    async def genres(self) -> tuple[Genre, ...]:
        data = await self._client.get("/genre/tv/list", {"language": self._language}, ttl=TTL_LISTS)
        return to_genres(data)

    async def search(self, query: str, page: int) -> CatalogPage:
        params = {"query": query[:MAX_QUERY], "page": str(page), "language": self._language,
                  "include_adult": "false"}
        result = to_catalog_page(await self._client.get("/search/tv", params, ttl=TTL_RESULTS))
        semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)
        cards = await asyncio.gather(*(self._with_providers(card, semaphore) for card in result.items))
        return dataclasses.replace(result, items=tuple(cards))

    async def _with_providers(self, card: SeriesCard, semaphore: asyncio.Semaphore) -> SeriesCard:
        try:
            async with semaphore:
                data = await self._client.get(f"/tv/{card.id}/watch/providers", ttl=TTL_DETAIL)
        except TMDBError:
            return card
        region_data = (data.get("results") or {}).get(self._region)
        return dataclasses.replace(card, providers=card_providers(region_data))

    async def detail(self, series_id: int) -> SeriesDetail:
        params = {"language": self._language, "append_to_response": DETAIL_APPEND,
                  "include_video_language": VIDEO_LANGUAGES}
        data = await self._client.get(f"/tv/{series_id}", params, ttl=TTL_DETAIL)
        fallback = ""
        if not data.get("overview"):
            try:
                english = await self._client.get(f"/tv/{series_id}", {"language": FALLBACK_LANGUAGE},
                                                 ttl=TTL_DETAIL)
                fallback = english.get("overview") or ""
            except TMDBError:
                pass
        return to_detail(data, self._region, overview_fallback=fallback)
