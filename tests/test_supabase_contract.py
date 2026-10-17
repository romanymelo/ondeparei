"""Contrato com o Supabase real: tabelas, RLS e funções de supabase/migracoes/001_marcacoes.sql.

Roda só com `uv run pytest -m supabase` (precisa de SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY e
SUPABASE_SECRET_KEY no .env). Cria dois usuários temporários e apaga os dois no fim.
"""

import secrets
import uuid

import httpx
import pytest

from app.auth.client import SupabaseAuth, admin_headers
from app.config import load_settings
from app.models import Marks
from app.tracking.supabase_repository import SupabaseTrackingRepository

pytestmark = pytest.mark.supabase


@pytest.fixture
async def people():
    settings = load_settings()
    if settings.supabase_secret_key is None:
        pytest.fail("SUPABASE_SECRET_KEY não definido no .env")
    url, key = settings.supabase_url, settings.supabase_publishable_key
    admin = admin_headers(settings.supabase_secret_key.get_secret_value())
    async with httpx.AsyncClient(timeout=15) as http:
        auth = SupabaseAuth(http, url, key)
        created, repos = [], []
        try:
            for _ in range(2):
                email, password = f"teste-{uuid.uuid4().hex[:10]}@ondeparei.test", secrets.token_urlsafe(16)
                r = await http.post(f"{url}/auth/v1/admin/users", headers=admin,
                                    json={"email": email, "password": password, "email_confirm": True})
                r.raise_for_status()
                created.append(r.json()["id"])
                session = await auth.sign_in(email, password)
                repos.append(SupabaseTrackingRepository(http, url, key, session.access_token))
            yield repos[0], repos[1], http, url, key
        finally:
            for user_id in created:
                await http.delete(f"{url}/auth/v1/admin/users/{user_id}", headers=admin)


async def test_save_and_read_back(people):
    a, *_ = people
    await a.save(42, name="Teste", poster_path=None, status="watching", favorite=True,
                 add=[(1, 1), (1, 2)], runtimes={(1, 1): 50})
    assert await a.marks(42) == Marks("watching", True)
    assert await a.watched(42) == {(1, 1), (1, 2)}
    assert [s.name for s in await a.list_tab("watching")] == ["Teste"]
    await a.save(42, name="Teste", poster_path=None, status="watching", favorite=True, add=[(1, 1)])  # repetir não dá erro


async def test_other_user_sees_nothing_and_cannot_change(people):
    a, b, *_ = people
    await a.save(42, name="Teste", poster_path=None, status="watching", favorite=False, add=[(1, 1)])
    assert await b.marks_for([42]) == {} and await b.watched(42) == frozenset()
    await b.save(42, name="Outro", poster_path=None, status="want", favorite=False, remove=[(1, 1)])
    assert await a.marks(42) == Marks("watching", False) and await a.watched(42) == {(1, 1)}
    assert await b.marks(42) == Marks("want", False)


async def test_anon_has_no_access(people):
    a, _, http, url, key = people
    await a.save(42, name="Teste", poster_path=None, status="watching", favorite=False)
    read = await http.get(f"{url}/rest/v1/series_tracking", params={"select": "tmdb_id"}, headers={"apikey": key})
    assert read.status_code == 401 or read.json() == []
    rpc = await http.post(f"{url}/rest/v1/rpc/watch_time", json={}, headers={"apikey": key})
    assert rpc.status_code >= 400


async def test_counts_watch_time_missing_and_set_runtimes(people):
    a, *_ = people
    await a.save(1, name="A", poster_path=None, status="watching", favorite=True, add=[(1, 1), (1, 2)],
                 runtimes={(1, 1): 50})
    await a.save(2, name="B", poster_path=None, status="watched", favorite=False, add=[(2, 1)])
    assert await a.counts() == {"watching": 1, "want": 0, "watched": 1, "favorite": 1}
    assert await a.watch_time() == (3, 50)
    assert await a.missing_runtimes() == {1: {1}, 2: {2}}
    await a.set_runtimes(1, {(1, 2): 40, (1, 1): 999})  # só preenche as que faltam
    assert await a.watch_time() == (3, 90)


async def test_empty_row_is_deleted(people):
    a, *_ = people
    await a.save(9, name="X", poster_path=None, status="want", favorite=False)
    await a.save(9, name="X", poster_path=None, status=None, favorite=False)
    assert await a.marks_for([9]) == {}
