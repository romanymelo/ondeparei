import base64
import json


from app.auth.client import AuthUnavailable
from app.auth.session import UserResolver
from tests.fakes import HX, TEST_USER, FakeAuth, tracked_catalog
from tests.helpers import FakeClock

ID = 100088


def jwt_with_exp(exp: int) -> str:
    """Token no formato JWT só com o "exp" (a assinatura não importa: quem confere é o Supabase)."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"cabecalho.{payload}.assinatura"


async def test_valid_token_is_cached():
    auth = FakeAuth({"tok": TEST_USER})
    resolver = UserResolver(auth, clock=FakeClock(1000))
    for _ in range(2):
        r = await resolver.resolve("tok", None)
        assert (r.user, r.access_token, r.new_session, r.clear) == (TEST_USER, "tok", None, False)
    assert [name for name, _ in auth.calls] == ["get_user"]


async def test_cache_never_outlives_token_expiry():
    clock = FakeClock(1000)
    token = jwt_with_exp(1010)
    auth = FakeAuth({token: TEST_USER})
    resolver = UserResolver(auth, clock=clock)
    await resolver.resolve(token, None)
    clock.t = 1011
    await resolver.resolve(token, None)
    assert [name for name, _ in auth.calls] == ["get_user", "get_user"]


async def test_expired_token_refreshes_and_returns_new_session():
    auth = FakeAuth({"ref-ok": TEST_USER})
    r = await UserResolver(auth, clock=FakeClock(1000)).resolve("tok-velho", "ref-ok")
    assert r.user == TEST_USER and r.new_session.access_token == "tok-renovado" and r.access_token == "tok-renovado"


async def test_only_refresh_token_also_renews():
    r = await UserResolver(FakeAuth({"ref-ok": TEST_USER}), clock=FakeClock(1000)).resolve(None, "ref-ok")
    assert r.user == TEST_USER and r.new_session is not None


async def test_revoked_refresh_clears_cookies():
    r = await UserResolver(FakeAuth({}), clock=FakeClock(1000)).resolve("tok-velho", "ref-revogado")
    assert (r.user, r.clear) == (None, True)


async def test_supabase_down_is_visitor_without_clearing():
    r = await UserResolver(FakeAuth(error=AuthUnavailable()), clock=FakeClock(1000)).resolve("tok", "ref")
    assert (r.user, r.clear, r.new_session) == (None, False, None)


def test_cookie_attributes(make_client):
    c = make_client(tracked_catalog(), user=None)
    c.app.state.auth.users_by_token["ref-ok"] = TEST_USER
    c.cookies.set("op_renovacao", "ref-ok")
    r = c.get(f"/serie/{ID}")
    cookies = r.headers.get_list("set-cookie")
    refresh = next(h for h in cookies if h.startswith("op_renovacao="))
    access = next(h for h in cookies if h.startswith("op_acesso="))
    for header in (refresh, access):
        assert "HttpOnly" in header and "SameSite=lax" in header and "Path=/" in header
    assert "Max-Age=15552000" in refresh


def test_htmx_action_with_expired_token_works_and_renews(make_client):
    c = make_client(tracked_catalog(), user=None)
    c.app.state.auth.users_by_token["ref-ok"] = TEST_USER
    c.cookies.set("op_acesso", "tok-velho")
    c.cookies.set("op_renovacao", "ref-ok")
    r = c.post(f"/serie/{ID}/status", data={"status": "want"}, headers=HX)
    assert r.status_code == 200 and 'id="status-serie"' in r.text
    assert any(h.startswith("op_acesso=tok-renovado") for h in r.headers.get_list("set-cookie"))


def test_revoked_session_becomes_visitor_without_error(make_client):
    c = make_client(tracked_catalog(), user=None)
    c.cookies.set("op_acesso", "tok-velho")
    c.cookies.set("op_renovacao", "ref-revogado")
    r = c.get(f"/serie/{ID}")
    assert r.status_code == 200
    cleared = [h for h in r.headers.get_list("set-cookie") if "Max-Age=0" in h]
    assert {h.split("=")[0] for h in cleared} == {"op_acesso", "op_renovacao"}


def test_supabase_down_logged_user_sees_series_page(make_client):
    c = make_client(tracked_catalog())
    c.app.state.auth.error = AuthUnavailable()
    r = c.get(f"/serie/{ID}")
    assert r.status_code == 200 and "Max-Age=0" not in r.headers.get("set-cookie", "")


def test_visitor_action_htmx_gets_hx_redirect(make_client):
    r = make_client(tracked_catalog(), user=None).post(
        f"/serie/{ID}/status", data={"status": "want"},
        headers=HX | {"HX-Current-URL": f"http://testserver/serie/{ID}"})
    assert r.status_code == 200 and r.headers["hx-redirect"] == f"/entrar?proximo=%2Fserie%2F{ID}"


def test_visitor_action_page_gets_303_to_login(make_client):
    r = make_client(tracked_catalog(), user=None).post(
        f"/serie/{ID}/status", data={"status": "want"}, headers={"Referer": f"http://testserver/serie/{ID}"},
        follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/entrar?proximo=%2Fserie%2F{ID}"


def test_visitor_my_series_redirects_to_login(make_client):
    r = make_client(tracked_catalog(), user=None).get("/minhas-series?aba=quero", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/entrar?proximo=%2Fminhas-series%3Faba%3Dquero"
