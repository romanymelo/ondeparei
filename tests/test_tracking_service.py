from datetime import date

import pytest

from app.models import Season
from app.tmdb.client import TMDBUnavailable
from app.tracking.db import connect
from app.tracking.repository import TrackingRepository
from app.tracking.service import InvalidAction, TrackingService
from tests.fakes import FakeCatalog, make_detail, make_season, tracked_catalog, tracked_detail

ID = 100088
TODAY = date(2026, 10, 17)


@pytest.fixture
def repo():
    conn = connect(":memory:")
    yield TrackingRepository(conn)
    conn.close()


def service(repo, catalog=None):
    return TrackingService(catalog or tracked_catalog(), repo, today=lambda: TODAY)


async def test_marking_an_episode_starts_watching(repo):
    view = await service(repo).toggle_episode(ID, 1, 1)
    assert view.watched == frozenset({(1, 1)}) and view.marks.status == "watching"
    assert view.progress == (1, 3) and view.next_episode == (1, 2)


async def test_toggling_twice_unmarks(repo):
    s = service(repo)
    await s.toggle_episode(ID, 1, 1)
    assert (await s.toggle_episode(ID, 1, 1)).watched == frozenset()


async def test_up_to_crosses_seasons_and_last_aired_means_watched(repo):
    s = service(repo)
    view = await s.mark_up_to(ID, 2, 2)
    assert repo.watched(ID) == {(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)} and view.marks.status == "watched"
    assert (await s.mark_up_to(ID, 2, 2)).marks.status == "watched"  # repetir não muda nada
    assert (await s.toggle_episode(ID, 1, 2)).marks.status == "watching"


async def test_whole_season_marks_then_unmarks(repo):
    s = service(repo)
    assert (await s.toggle_season(ID, 1)).progress == (3, 3)
    assert (await s.toggle_season(ID, 1)).progress == (0, 3)


@pytest.mark.parametrize(("season", "episode"), [(2, 3), (5, 1), (1, 0)])
async def test_unaired_or_unknown_episode_is_refused(repo, season, episode):
    with pytest.raises(InvalidAction):
        await service(repo).toggle_episode(ID, season, episode)
    assert repo.marks_for([ID]) == {}


async def test_tmdb_failure_saves_nothing(repo):
    with pytest.raises(TMDBUnavailable):
        await service(repo, tracked_catalog(error=TMDBUnavailable("fora"))).toggle_episode(ID, 1, 1)
    assert repo.marks_for([ID]) == {}


async def test_status_toggles_off_and_is_validated(repo):
    s = service(repo)
    assert (await s.set_status(ID, "want")).marks.status == "want"
    assert (await s.set_status(ID, "want")).marks.status is None
    with pytest.raises(InvalidAction):
        await s.set_status(ID, "xyz")


async def test_marking_watched_marks_every_aired_episode(repo):
    t = await service(repo).set_status(ID, "watched")
    assert repo.watched(ID) == {(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)}  # T2E3 ainda não estreou
    assert t.marks.status == "watched" and t.season_progress == {1: (3, 3), 2: (2, 2)}


async def test_marking_watched_skips_specials(repo):
    detail = make_detail(seasons=(Season(0, "Especiais", None, 2, None), Season(1, "Temporada 1", 2023, 3, None)),
                         last_aired=(1, 3))
    await service(repo, FakeCatalog(detail=detail)).set_status(ID, "watched")
    assert repo.watched(ID) == {(1, 1), (1, 2), (1, 3)}


@pytest.mark.parametrize(("new_status", "expected"), [("watched", None), ("want", "want"), ("watching", "watching")])
async def test_leaving_watched_clears_every_episode(repo, new_status, expected):
    detail = make_detail(seasons=(Season(0, "Especiais", None, 2, None), Season(1, "Temporada 1", 2023, 3, None)),
                         last_aired=(1, 3))
    s = service(repo, FakeCatalog(detail=detail, seasons={0: make_season(0, 2), 1: make_season(1, 3)}))
    await s.set_status(ID, "watched")
    await s.toggle_episode(ID, 0, 1)  # especial marcado à mão
    t = await s.set_status(ID, new_status)  # "watched" de novo = desmarcar Assistido
    assert t.marks.status == expected and repo.watched(ID) == frozenset()
    assert t.season_progress == {0: (0, 0), 1: (0, 3)}


async def test_other_status_changes_keep_the_episodes(repo):
    s = service(repo)
    await s.toggle_episode(ID, 1, 1)  # Assistindo com T1E1
    await s.set_status(ID, "want")
    assert repo.watched(ID) == {(1, 1)}


async def test_favorite_toggles_and_saves_snapshot(repo):
    assert (await service(repo).toggle_favorite(ID)).marks.favorite is True
    item = repo.list_tab("favorite")[0]
    assert (item.name, item.poster_url) == ("The Last of Us", "https://image.tmdb.org/t/p/w342/tlou.jpg")


async def test_series_tracking_has_next_title_and_season_progress(repo):
    s = service(repo)
    await s.toggle_episode(ID, 1, 1)
    t = await s.series(tracked_detail())
    assert (t.next_episode, t.next_title) == ((1, 2), "Episódio 2")
    assert t.season_progress == {1: (1, 3), 2: (0, 2)}


async def test_watched_episodes_outside_aired_do_not_inflate_progress(repo):
    repo.save(ID, name="x", poster_path=None, status="watching", favorite=False, add=[(1, 1), (2, 3), (7, 1)])
    t = await service(repo).series(tracked_detail())
    assert t.season_progress == {1: (1, 3), 2: (0, 2)} and t.next_episode == (1, 2)


async def test_specials_count_by_date_and_never_change_status(repo):
    detail = make_detail(seasons=(Season(0, "Especiais", None, 2, None), Season(1, "Temporada 1", 2023, 3, None)),
                         last_aired=(1, 3))
    s = service(repo, FakeCatalog(detail=detail, seasons={0: make_season(0, 2, future_from=2), 1: make_season(1, 3)}))
    view = await s.toggle_episode(ID, 0, 1)
    assert view.marks.status is None and view.progress == (1, 1)
    with pytest.raises(InvalidAction):
        await s.toggle_episode(ID, 0, 2)
    assert (await s.series(detail)).season_progress[0] == (1, 0)


async def test_my_series_watching_tab(repo):
    details = {ID: tracked_detail(), 1399: tracked_detail(id=1399, name="Outra")}
    s = service(repo, tracked_catalog(details=details))
    await s.toggle_episode(ID, 1, 1)
    repo.save(1399, name="Outra", poster_path=None, status="watching", favorite=False,  # tudo visto: em dia
              add=[(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)])
    repo.save(777, name="Sumiu", poster_path=None, status="watching", favorite=False)  # some da TMDB
    view = await s.my_series("assistindo")
    by_id = {i.tmdb_id: i for i in view.items}
    assert (by_id[ID].next_episode, by_id[ID].progress, by_id[ID].caught_up) == ((1, 2), (1, 5), False)
    assert (by_id[1399].next_episode, by_id[1399].caught_up) == (None, True)
    assert (by_id[777].next_episode, by_id[777].progress) == (None, None)
    assert view.tab == "assistindo" and view.counts["assistindo"] == 3


async def test_my_series_unknown_tab_falls_back(repo):
    assert (await service(repo).my_series("xyz")).tab == "assistindo"


async def test_specials_keep_manual_status_with_normal_episodes_marked(repo):
    detail = make_detail(seasons=(Season(0, "Especiais", None, 2, None), Season(1, "Temporada 1", 2023, 3, None)),
                         last_aired=(1, 3))
    s = service(repo, FakeCatalog(detail=detail, seasons={0: make_season(0, 2), 1: make_season(1, 3)}))
    await s.toggle_episode(ID, 1, 1)
    await s.set_status(ID, "want")
    assert (await s.toggle_episode(ID, 0, 1)).marks.status == "want"
    assert (await s.toggle_episode(ID, 0, 1)).marks.status == "want"


async def test_unmarking_a_whole_watched_series_clears_the_status(repo):
    s = service(repo)
    assert (await s.mark_up_to(ID, 2, 2)).marks.status == "watched"
    await s.toggle_season(ID, 2)
    assert (await s.toggle_season(ID, 1)).marks.status is None
    assert repo.marks_for([ID]) == {}  # sem status, favorito nem episódios: a linha some
