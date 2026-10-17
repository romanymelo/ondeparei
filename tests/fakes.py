"""Dublês de teste para as rotas: um Catalog falso e construtores de modelos."""

from datetime import date
from typing import Any

from app.models import (CastMember, CatalogPage, Episode, Provider, Season, SeasonDetail, SeriesCard, SeriesDetail,
                        Spotlight, WatchOptions)
from app.tmdb.client import TMDBNotFound

HX = {"HX-Request": "true"}


def make_card(id: int = 1, name: str = "Série 1", **kw: Any) -> SeriesCard:
    fields = {"year": 2023, "rating": 8.6, "poster_url": None, "providers": None} | kw
    return SeriesCard(id=id, name=name, **fields)


def make_page(n: int = 3, page: int = 1, total_pages: int = 1, total_results: int | None = None) -> CatalogPage:
    items = tuple(make_card(i, f"Série {i}") for i in range(1, n + 1))
    return CatalogPage(items, page, total_pages, n if total_results is None else total_results)


def make_detail(**kw: Any) -> SeriesDetail:
    fields = {
        "id": 100088,
        "name": "The Last of Us",
        "original_name": "The Last of Us",
        "overview": "Vinte anos após a destruição da civilização moderna, Joel é contratado para tirar Ellie da zona de quarentena.",
        "first_year": 2023,
        "last_year": 2025,
        "years_label": "2023–",
        "status_label": "Em exibição",
        "in_production": True,
        "seasons_count": 2,
        "episodes_count": 16,
        "genres": ("Drama", "Action & Adventure"),
        "rating": 8.6,
        "vote_count": 5231,
        "poster_url": None,
        "backdrop_url": None,
        "trailer_youtube_key": "abc123",
        "seasons": (Season(1, "Temporada 1", 2023, 9, None),),
        "cast": (CastMember("Pedro Pascal", "Joel", None),),
        "watch": WatchOptions(
            link="https://www.themoviedb.org/tv/100088/watch?locale=BR",
            by_type={"flatrate": (Provider(1899, "Max", "https://image.tmdb.org/t/p/w92/max.png"),)},
        ),
        "poster_path": "/tlou.jpg",
        "last_aired": (1, 9),
    } | kw
    return SeriesDetail(**fields)


def make_episode(season: int, number: int, **kw: Any) -> Episode:
    fields = {"name": f"Episódio {number}", "overview": "", "air_date": date(2023, 1, number), "runtime": 50,
              "still_url": None} | kw
    return Episode(season=season, number=number, **fields)


def make_season(number: int = 1, count: int = 3, future_from: int | None = None) -> SeasonDetail:
    """Temporada com `count` episódios; a partir de `future_from`, eles estreiam em 01/01/2027."""
    episodes = tuple(
        make_episode(number, n, **({"air_date": date(2027, 1, 1)} if future_from and n >= future_from else {}))
        for n in range(1, count + 1))
    return SeasonDetail(100088, number, "Especiais" if number == 0 else f"Temporada {number}", episodes)


def tracked_detail(**kw: Any) -> SeriesDetail:
    """T1 com 3 episódios e T2 com 3, exibidos até T2E2."""
    fields = {"seasons": (Season(1, "Temporada 1", 2023, 3, None), Season(2, "Temporada 2", 2025, 3, None)),
              "last_aired": (2, 2)} | kw
    return make_detail(**fields)


def make_spotlight(**kw: Any) -> Spotlight:
    fields = {
        "id": 1396,
        "name": "Breaking Bad",
        "year": 2008,
        "rating": 9.0,
        "overview": "Um professor de química com câncer terminal passa a fabricar metanfetamina para garantir o futuro da família.",
        "backdrop_url": "https://image.tmdb.org/t/p/w1280/bb.jpg",
        "genres": ("Drama", "Crime"),
        "providers": (Provider(8, "Netflix", "https://image.tmdb.org/t/p/w92/n.png"),),
    } | kw
    return Spotlight(**fields)


class FakeCatalog:
    """Mesma interface do Catalog; devolve valores configurados ou lança o erro configurado."""

    def __init__(self, *, discover=None, providers=(), genres=(), search=None, detail=None, spotlight=None,
                 error=None, providers_error=None, genres_error=None, spotlight_error=None,
                 seasons=None, details=None) -> None:
        self._seasons = seasons or {}
        self._details = details
        self._results = {"discover": discover, "providers": providers, "genres": genres,
                         "search": search, "detail": detail, "spotlight": spotlight}
        self._errors = {"providers": providers_error, "genres": genres_error, "spotlight": spotlight_error}
        self._error = error
        self.calls: list[tuple[str, tuple]] = []

    async def _answer(self, name: str, *args: Any) -> Any:
        self.calls.append((name, args))
        error = self._errors.get(name) or self._error
        if error is not None:
            raise error
        return self._results[name]

    async def discover(self, filters):
        return await self._answer("discover", filters)

    async def providers(self):
        return await self._answer("providers")

    async def genres(self):
        return await self._answer("genres")

    async def search(self, query, page):
        return await self._answer("search", query, page)

    async def detail(self, series_id):
        if self._details is not None:
            await self._answer("detail", series_id)
            if series_id not in self._details:
                raise TMDBNotFound(f"série {series_id}")
            return self._details[series_id]
        return await self._answer("detail", series_id)

    async def season(self, series_id, number):
        self.calls.append(("season", (series_id, number)))
        if self._error is not None:
            raise self._error
        if number not in self._seasons:
            raise TMDBNotFound(f"temporada {number}")
        return self._seasons[number]

    async def spotlight(self):
        return await self._answer("spotlight")


def tracked_catalog(detail: SeriesDetail | None = None, **kw: Any) -> FakeCatalog:
    """Catálogo da série 100088: T1 toda exibida; T2 com E1–E2 exibidos e E3 estreando em 01/01/2027."""
    seasons = {1: make_season(1, 3), 2: make_season(2, 3, future_from=3)}
    return FakeCatalog(detail=detail or tracked_detail(), seasons=seasons, **kw)
