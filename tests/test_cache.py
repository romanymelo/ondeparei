from app.tmdb.cache import TTLCache, make_key
from tests.helpers import FakeClock


def test_value_available_before_ttl():
    clock = FakeClock()
    c = TTLCache(clock=clock)
    c.set("k", 1, ttl=10)
    clock.t = 9.9
    assert c.get("k") == 1


def test_value_expires_at_ttl():
    clock = FakeClock()
    c = TTLCache(clock=clock)
    c.set("k", 1, ttl=10)
    clock.t = 10
    assert c.get("k") is None and len(c) == 0


def test_evicts_least_recently_used():
    c = TTLCache(max_entries=2, clock=FakeClock())
    c.set("a", 1, ttl=60)
    c.set("b", 2, ttl=60)
    c.get("a")
    c.set("c", 3, ttl=60)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3


def test_set_overwrites_value_and_ttl():
    clock = FakeClock()
    c = TTLCache(clock=clock)
    c.set("k", 1, ttl=5)
    clock.t = 4
    c.set("k", 2, ttl=5)
    clock.t = 8
    assert c.get("k") == 2


def test_make_key_ignores_param_order():
    assert make_key("/x", {"a": 1, "b": 2}) == make_key("/x", {"b": 2, "a": 1})
    assert make_key("/x", {"a": 1}) != make_key("/y", {"a": 1})
