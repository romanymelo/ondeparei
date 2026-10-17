from datetime import date

import pytest

from app.models import Episode
from app.tracking.rules import (aired_episodes, aired_specials, auto_status, next_episode, progress,
                                season_episodes, up_to)

AIRED = aired_episodes([(1, 3), (2, 4)], (2, 2))  # T1E1–T1E3, T2E1–T2E2


def test_aired_episodes_until_last_aired():
    assert AIRED == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)]


def test_aired_episodes_empty_without_last_aired():
    assert aired_episodes([(1, 3)], None) == []


def test_aired_episodes_ignore_specials():
    assert aired_episodes([(0, 5), (1, 2)], (1, 2)) == [(1, 1), (1, 2)]


def special(n, air_date):
    return Episode(0, n, f"Especial {n}", "", air_date, None, None)


def test_aired_specials_by_air_date():
    episodes = [special(1, date(2026, 10, 16)), special(2, date(2026, 10, 17)), special(3, None)]
    assert aired_specials(episodes, today=date(2026, 10, 16)) == [(0, 1)]


def test_next_episode_is_first_aired_not_watched():
    assert next_episode(AIRED, {(1, 1), (1, 3)}) == (1, 2)
    assert next_episode(AIRED, set(AIRED)) is None


def test_up_to_crosses_seasons():
    assert up_to(AIRED, (2, 1)) == [(1, 1), (1, 2), (1, 3), (2, 1)]


def test_season_episodes():
    assert season_episodes(AIRED, 2) == [(2, 1), (2, 2)]


@pytest.mark.parametrize(("current", "watched", "expected"), [
    (None, set(AIRED), "watched"),
    ("want", set(AIRED), "watched"),
    ("want", {(1, 1)}, "watching"),
    ("watched", {(1, 1)}, "watching"),  # Assistido manual + 1 episódio → Assistindo
    (None, set(), None),
    ("want", set(), "want"),
    ("want", {(0, 1)}, "want"),         # especiais não contam
    ("watched", {(3, 1)}, None),        # marcado fora dos exibidos não conta: ficou sem nada → sem status
    ("watched", set(), None),           # desmarcou tudo: "Assistido" sem nada assistido vira sem status
    ("watching", set(), None),          # idem para "Assistindo" sem nada marcado
])
def test_auto_status(current, watched, expected):
    assert auto_status(current, AIRED, watched) == expected


def test_auto_status_without_aired_keeps_current():
    assert auto_status("want", [], {(1, 1)}) == "want"


def test_progress_counts_only_aired():
    assert progress(season_episodes(AIRED, 1), {(1, 1), (0, 2), (2, 1), (1, 9)}) == (1, 3)
