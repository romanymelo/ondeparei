"""Regras puras das marcações. Episódios são pares (temporada, episódio); a temporada 0 é a dos Especiais."""

from collections.abc import Collection, Iterable, Sequence
from datetime import date

from app.models import Episode

Ep = tuple[int, int]


def aired_episodes(seasons: Iterable[tuple[int, int]], last_aired: Ep | None) -> list[Ep]:
    """Episódios já exibidos, em ordem, a partir de (número, episode_count) de cada temporada (sem Especiais)."""
    if last_aired is None:
        return []
    return [(number, episode)
            for number, count in sorted(seasons) if number >= 1
            for episode in range(1, count + 1) if (number, episode) <= last_aired]


def aired_specials(episodes: Iterable[Episode], today: date) -> list[Ep]:
    """Especiais já exibidos: o last_episode_to_air não cobre a temporada 0, então vale a data de cada um."""
    return [(e.season, e.number) for e in episodes if e.air_date is not None and e.air_date <= today]


def next_episode(aired: Sequence[Ep], watched: Collection[Ep]) -> Ep | None:
    return next((episode for episode in aired if episode not in watched), None)


def up_to(aired: Sequence[Ep], target: Ep) -> list[Ep]:
    return [episode for episode in aired if episode <= target]


def season_episodes(aired: Sequence[Ep], season: int) -> list[Ep]:
    return [episode for episode in aired if episode[0] == season]


def auto_status(current: str | None, aired: Sequence[Ep], watched: Collection[Ep]) -> str | None:
    """Status depois de uma ação nos episódios: todos os exibidos → watched; alguns → watching; nenhum → só
    "Quero assistir" se mantém (sem nada assistido, "Assistindo" e "Assistido" ficam sem status)."""
    seen = sum(1 for episode in aired if episode in watched)
    if aired and seen == len(aired):
        return "watched"
    if seen:
        return "watching"
    return "want" if current == "want" else None


def progress(aired: Iterable[Ep], watched: Collection[Ep]) -> tuple[int, int]:
    """(marcados, exibidos), contando só os marcados que estão entre os exibidos."""
    aired = list(aired)
    return sum(1 for episode in aired if episode in watched), len(aired)
