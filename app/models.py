from dataclasses import dataclass
from datetime import date

ALL_TYPES = ("flatrate", "free", "ads", "rent", "buy")


@dataclass(frozen=True)
class Filters:
    providers: tuple[int, ...] = ()
    genres: tuple[int, ...] = ()
    min_rating: int | None = None
    sort: str = "popularidade"
    page: int = 1

    @property
    def active_count(self) -> int:
        return sum((bool(self.providers), bool(self.genres), self.min_rating is not None))


@dataclass(frozen=True)
class Provider:
    id: int
    name: str
    logo_url: str | None
    variant_ids: tuple[int, ...] = ()  # outras versões do mesmo serviço: "Paramount+ Amazon Channel", "Premium"...

    @property
    def ids(self) -> tuple[int, ...]:
        return (self.id, *self.variant_ids)


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
    poster_path: str | None = None  # guardado no banco (snapshot) quando a série é marcada
    last_aired: tuple[int, int] | None = None  # (temporada, episódio) do último episódio exibido
    typical_runtime: int | None = None  # minutos; usado quando a TMDB não informa a duração de um episódio


@dataclass(frozen=True)
class Spotlight:
    """Série em destaque no topo da tela inicial."""

    id: int
    name: str
    year: int | None
    rating: float | None
    overview: str
    backdrop_url: str
    genres: tuple[str, ...]
    providers: tuple[Provider, ...]


@dataclass(frozen=True)
class Episode:
    season: int
    number: int
    name: str
    overview: str
    air_date: date | None
    runtime: int | None
    still_url: str | None


@dataclass(frozen=True)
class SeasonDetail:
    series_id: int
    number: int
    name: str
    episodes: tuple[Episode, ...]


@dataclass(frozen=True)
class Marks:
    """Marcações de uma série: status (want/watching/watched ou None) e favorita."""

    status: str | None = None
    favorite: bool = False


@dataclass(frozen=True)
class TrackedSeries:
    """Cartão de Minhas séries."""

    tmdb_id: int
    name: str
    poster_url: str | None
    marks: Marks
    next_episode: tuple[int, int] | None = None
    caught_up: bool = False
    progress: tuple[int, int] | None = None  # (marcados, exibidos); só na aba Assistindo
    new_episodes: int = 0  # aba Assistidas: episódios já exibidos ainda não marcados
    new_season: bool = False  # aba Assistidas: estreou uma temporada da qual nada foi visto


@dataclass(frozen=True)
class SeriesTracking:
    """Bloco de status da página da série e o progresso de cada temporada."""

    marks: Marks
    next_episode: tuple[int, int] | None
    next_title: str | None
    season_progress: dict[int, tuple[int, int]]  # temporada -> (marcados, exibidos); Especiais -> (marcados, 0)


@dataclass(frozen=True)
class SeasonView:
    """Página da temporada: os episódios e o que já foi marcado e exibido nela."""

    detail: SeriesDetail
    season: SeasonDetail
    marks: Marks
    watched: frozenset[tuple[int, int]]
    aired: frozenset[tuple[int, int]]
    next_episode: tuple[int, int] | None

    @property
    def progress(self) -> tuple[int, int]:
        return len(self.watched & self.aired), len(self.aired)

    @property
    def complete(self) -> bool:
        return bool(self.aired) and self.aired <= self.watched


@dataclass(frozen=True)
class MySeries:
    tab: str
    counts: dict[str, int]  # chaves da URL: assistindo, quero, assistidas, favoritas
    items: tuple[TrackedSeries, ...]
    watch_time: tuple[int, int] = (0, 0)  # (episódios marcados, minutos assistidos)
