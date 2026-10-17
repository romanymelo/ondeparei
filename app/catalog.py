"""Serviço do catálogo: orquestra as chamadas à TMDB e devolve modelos do domínio."""

import asyncio
import dataclasses
from collections.abc import Callable
from datetime import date

from app.filters import MAX_PAGE, discover_params
from app.mappers import card_providers, to_card, to_catalog_page, to_detail, to_genres, to_provider_list
from app.models import CatalogPage, Filters, Genre, Provider, SeriesCard, SeriesDetail
from app.tmdb.client import TMDBClient, TMDBError

TTL_LISTS = 24 * 3600
TTL_DETAIL = 6 * 3600
TTL_RESULTS = 3600
SEARCH_CONCURRENCY = 10
MAX_QUERY = 100
PAGE_SIZE = 50  # séries por "Carregar mais" no catálogo
TMDB_PAGE_SIZE = 20  # fixo na TMDB
MAX_RESULTS = MAX_PAGE * TMDB_PAGE_SIZE  # o /discover/tv para em 500 páginas


def _total_pages(tmdb_data: dict) -> int:
    reachable = min(tmdb_data.get("total_results", 0), MAX_RESULTS)
    return -(-reachable // PAGE_SIZE)
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
        """Página de PAGE_SIZE séries montada a partir das páginas de 20 da TMDB que cobrem o intervalo."""
        params = discover_params(filters, self._region, self._language, self._today())
        start = (filters.page - 1) * PAGE_SIZE
        first_page = start // TMDB_PAGE_SIZE + 1
        last_page = (start + PAGE_SIZE - 1) // TMDB_PAGE_SIZE + 1
        if first_page > MAX_PAGE:
            head = await self._discover_page(params, 1)
            return CatalogPage((), filters.page, _total_pages(head), head.get("total_results", 0))

        head = await self._discover_page(params, first_page)
        available = min(last_page, head.get("total_pages", 0), MAX_PAGE)
        rest = await asyncio.gather(*(self._discover_page(params, n) for n in range(first_page + 1, available + 1)))
        results = [item for data in (head, *rest) for item in data.get("results", [])]
        offset = start - (first_page - 1) * TMDB_PAGE_SIZE
        items = tuple(to_card(item) for item in results[offset:offset + PAGE_SIZE])
        return CatalogPage(items, filters.page, _total_pages(head), head.get("total_results", 0))

    async def _discover_page(self, params: dict[str, str], tmdb_page: int) -> dict:
        return await self._client.get("/discover/tv", {**params, "page": str(tmdb_page)}, ttl=TTL_RESULTS)

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
