"""Dublês de teste para as rotas: um Catalog falso e construtores de modelos."""

from typing import Any

from app.models import CastMember, CatalogPage, Provider, Season, SeriesCard, SeriesDetail, WatchOptions

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
    } | kw
    return SeriesDetail(**fields)


class FakeCatalog:
    """Mesma interface do Catalog; devolve valores configurados ou lança o erro configurado."""

    def __init__(self, *, discover=None, providers=(), genres=(), search=None, detail=None,
                 error=None, providers_error=None, genres_error=None) -> None:
        self._results = {"discover": discover, "providers": providers, "genres": genres,
                         "search": search, "detail": detail}
        self._errors = {"providers": providers_error, "genres": genres_error}
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
        return await self._answer("detail", series_id)
