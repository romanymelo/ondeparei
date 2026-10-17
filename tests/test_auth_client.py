import json

import httpx
import pytest
import respx

from app.auth.client import (AuthUnavailable, EmailTaken, InvalidCredentials, InvalidRecoveryLink, InvalidSession,
                             RateLimited, Session, SupabaseAuth, User, WeakPassword)

URL = "https://proj.supabase.co"
SESSION = {"access_token": "a1", "refresh_token": "r1", "expires_at": 2000000000,
           "user": {"id": "u-1", "email": "eu@x.com", "user_metadata": {"first_name": "Romany", "last_name": "Melo"}}}
USER = User("u-1", "eu@x.com", "Romany", "Melo")


@pytest.fixture
async def auth():
    async with httpx.AsyncClient(timeout=10) as http:
        yield SupabaseAuth(http, URL, "pk")


@pytest.fixture
def mock():
    with respx.mock(base_url=f"{URL}/auth/v1") as m:
        yield m


def body(route):
    return json.loads(route.calls.last.request.content)


async def test_sign_up_sends_names_and_returns_session(auth, mock):
    route = mock.post("/signup").respond(json=SESSION)
    s = await auth.sign_up("eu@x.com", "segredo123", "Romany", "Melo")
    assert body(route) == {"email": "eu@x.com", "password": "segredo123",
                           "data": {"first_name": "Romany", "last_name": "Melo"}}
    assert route.calls.last.request.headers["apikey"] == "pk"
    assert s == Session("a1", "r1", 2000000000, USER)


@pytest.mark.parametrize(("status", "payload", "error"), [
    (400, {"error_code": "invalid_credentials"}, InvalidCredentials),
    (422, {"error_code": "user_already_exists"}, EmailTaken),
    (422, {"error_code": "email_exists"}, EmailTaken),
    (422, {"error_code": "weak_password"}, WeakPassword),
    (429, {"error_code": "over_request_rate_limit"}, RateLimited),
    (503, {}, AuthUnavailable),
])
async def test_errors_are_translated(auth, mock, status, payload, error):
    mock.post("/signup").respond(status, json=payload)
    mock.post("/token").respond(status, json=payload)
    with pytest.raises(error):
        await auth.sign_up("eu@x.com", "segredo123", "Romany", "Melo")
    with pytest.raises(error):
        await auth.sign_in("eu@x.com", "segredo123")


async def test_network_error_and_non_json_are_unavailable(auth, mock):
    mock.post("/token").mock(side_effect=httpx.ConnectError("fora"))
    with pytest.raises(AuthUnavailable):
        await auth.sign_in("eu@x.com", "x")
    mock.post("/signup").respond(200, content=b"<html>")
    with pytest.raises(AuthUnavailable):
        await auth.sign_up("eu@x.com", "segredo123", "R", "M")


async def test_sign_in_uses_password_grant(auth, mock):
    route = mock.post("/token").respond(json=SESSION)
    s = await auth.sign_in("eu@x.com", "segredo123")
    assert route.calls.last.request.url.params["grant_type"] == "password"
    assert body(route) == {"email": "eu@x.com", "password": "segredo123"} and s.user == USER


async def test_expires_at_falls_back_to_expires_in(auth, mock, monkeypatch):
    monkeypatch.setattr("app.auth.client.time.time", lambda: 1000)
    mock.post("/token").respond(json={**SESSION, "expires_at": None, "expires_in": 3600})
    assert (await auth.sign_in("eu@x.com", "x")).expires_at == 4600


async def test_refresh_uses_refresh_grant(auth, mock):
    route = mock.post("/token").respond(json=SESSION)
    await auth.refresh("r0")
    assert route.calls.last.request.url.params["grant_type"] == "refresh_token"
    assert body(route) == {"refresh_token": "r0"}


@pytest.mark.parametrize(("status", "payload"), [(400, {"error_code": "refresh_token_not_found"}), (401, {}), (403, {})])
async def test_refused_refresh_is_invalid_session(auth, mock, status, payload):
    mock.post("/token").respond(status, json=payload)
    with pytest.raises(InvalidSession):
        await auth.refresh("r0")


async def test_get_user_sends_bearer(auth, mock):
    route = mock.get("/user").respond(json=SESSION["user"])
    assert await auth.get_user("a1") == USER
    assert route.calls.last.request.headers["authorization"] == "Bearer a1"


async def test_get_user_without_names_and_401(auth, mock):
    mock.get("/user").respond(json={"id": "u-2", "email": "b@x.com"})
    assert await auth.get_user("a1") == User("u-2", "b@x.com", "", "")
    mock.get("/user").respond(401, json={"error_code": "bad_jwt"})
    with pytest.raises(InvalidSession):
        await auth.get_user("a1")


async def test_recover_and_verify_recovery(auth, mock):
    recover = mock.post("/recover").respond(json={})
    await auth.recover("eu@x.com")
    assert body(recover) == {"email": "eu@x.com"}
    verify = mock.post("/verify").respond(json=SESSION)
    assert (await auth.verify_recovery("th")).access_token == "a1"
    assert body(verify) == {"type": "recovery", "token_hash": "th"}
    mock.post("/verify").respond(403, json={"error_code": "otp_expired"})
    with pytest.raises(InvalidRecoveryLink):
        await auth.verify_recovery("th")


async def test_update_password_puts_with_bearer(auth, mock):
    route = mock.put("/user").respond(json=SESSION["user"])
    await auth.update_password("a1", "nova-senha-1")
    assert body(route) == {"password": "nova-senha-1"}
    assert route.calls.last.request.headers["authorization"] == "Bearer a1"


async def test_sign_out_posts_logout_for_this_session_only(auth, mock):
    route = mock.post("/logout").respond(204)
    await auth.sign_out("a1")
    assert route.calls.last.request.url.params["scope"] == "local"
    assert route.calls.last.request.headers["authorization"] == "Bearer a1"


def test_admin_headers_new_and_legacy_keys():
    from app.auth.client import admin_headers
    assert admin_headers("sb_secret_abc") == {"apikey": "sb_secret_abc"}
    assert admin_headers("eyJ.legacy") == {"apikey": "eyJ.legacy", "Authorization": "Bearer eyJ.legacy"}


async def test_sign_up_without_session_means_confirmation_required(auth, mock):
    from app.auth.client import ConfirmationRequired
    mock.post("/signup").respond(json={"id": "u-1", "email": "eu@x.com", "user_metadata": {}})
    with pytest.raises(ConfirmationRequired):
        await auth.sign_up("eu@x.com", "segredo123", "R", "M")


@pytest.mark.parametrize(("code", "error_name"), [("email_address_invalid", "InvalidEmail"),
                                                 ("same_password", "SamePassword")])
async def test_more_error_codes(auth, mock, code, error_name):
    import app.auth.client as client
    mock.post("/signup").respond(400, json={"error_code": code})
    error = getattr(client, error_name)
    with pytest.raises(error):
        await auth.sign_up("eu@x.com", "segredo123", "R", "M")


async def test_recover_with_pkce_and_exchange_code(auth, mock):
    route = mock.post("/recover").respond(json={})
    await auth.recover("eu@x.com", redirect_to="http://localhost:8000/nova-senha", code_challenge="ch")
    assert route.calls.last.request.url.params["redirect_to"] == "http://localhost:8000/nova-senha"
    assert body(route) == {"email": "eu@x.com", "code_challenge": "ch", "code_challenge_method": "s256"}
    token = mock.post("/token").respond(json=SESSION)
    assert (await auth.exchange_code("abc", "ver")).access_token == "a1"
    assert token.calls.last.request.url.params["grant_type"] == "pkce"
    assert body(token) == {"auth_code": "abc", "code_verifier": "ver"}
    mock.post("/token").respond(400, json={"error_code": "flow_state_not_found"})
    with pytest.raises(InvalidRecoveryLink):
        await auth.exchange_code("abc", "ver")
