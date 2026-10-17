import pytest

from app.templating import format_watch_time, watch_time_parts, watch_time_units


@pytest.mark.parametrize(("minutes", "text"), [
    (0, "0 horas"),
    (59, "0 horas"),
    (60, "1 hora"),
    (125, "2 horas"),
    (25 * 60, "1 dia 1 hora"),
    (2 * 24 * 60, "2 dias"),
    (30 * 24 * 60, "1 mês"),
    ((65 * 24 + 7) * 60 + 30, "2 meses 5 dias 7 horas"),
])
def test_watch_time_like_tv_time(minutes, text):
    assert format_watch_time(minutes) == text


@pytest.mark.parametrize(("minutes", "parts"), [(0, (0, 0, 0)), (250, (0, 0, 4)), ((65 * 24 + 7) * 60 + 30, (2, 5, 7))])
def test_watch_time_parts(minutes, parts):
    assert watch_time_parts(minutes) == parts


@pytest.mark.parametrize(("minutes", "units"), [
    (0, [(0, "horas")]),
    ((22 * 24 + 23) * 60, [(22, "dias"), (23, "horas")]),
    ((61 * 24 + 1) * 60, [(2, "meses"), (1, "dia"), (1, "hora")]),
    ((60 * 24 + 7) * 60, [(2, "meses"), (0, "dias"), (7, "horas")]),
])
def test_header_units_start_at_the_first_non_zero(minutes, units):
    assert watch_time_units(minutes) == units
