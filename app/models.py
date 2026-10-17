from dataclasses import dataclass

ALL_TYPES = ("flatrate", "free", "ads", "rent", "buy")


@dataclass(frozen=True)
class Filters:
    providers: tuple[int, ...] = ()
    types: tuple[str, ...] = ALL_TYPES
    genres: tuple[int, ...] = ()
    year_from: int | None = None
    year_to: int | None = None
    min_rating: int | None = None
    sort: str = "popularidade"
    page: int = 1

    @property
    def active_count(self) -> int:
        return sum((
            bool(self.providers),
            set(self.types) != set(ALL_TYPES),
            bool(self.genres),
            self.year_from is not None or self.year_to is not None,
            self.min_rating is not None,
        ))


@dataclass(frozen=True)
class Provider:
    id: int
    name: str
    logo_url: str | None


@dataclass(frozen=True)
class Genre:
    id: int
    name: str


@dataclass(frozen=True)
class SeriesCard:
    id: int
    name: str
    year: int | None
    rating: float | None
    poster_url: str | None
    providers: tuple[Provider, ...] | None = None


@dataclass(frozen=True)
class CatalogPage:
    items: tuple[SeriesCard, ...]
    page: int
    total_pages: int
    total_results: int


@dataclass(frozen=True)
class WatchOptions:
    link: str | None
    by_type: dict[str, tuple[Provider, ...]]


@dataclass(frozen=True)
class Season:
    number: int
    name: str
    year: int | None
    episode_count: int
    poster_url: str | None


@dataclass(frozen=True)
class CastMember:
    name: str
    character: str
    profile_url: str | None


@dataclass(frozen=True)
class SeriesDetail:
    id: int
    name: str
    original_name: str
    overview: str
    first_year: int | None
    last_year: int | None
    years_label: str
    status_label: str
    in_production: bool
    seasons_count: int
    episodes_count: int
    genres: tuple[str, ...]
    rating: float | None
    vote_count: int
    poster_url: str | None
    backdrop_url: str | None
    trailer_youtube_key: str | None
    seasons: tuple[Season, ...]
    cast: tuple[CastMember, ...]
    watch: WatchOptions
