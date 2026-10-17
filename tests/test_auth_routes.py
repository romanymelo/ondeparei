from app.auth.client import AuthUnavailable, EmailTaken, InvalidRecoveryLink, User
from tests.fakes import TEST_USER, tracked_catalog

ID = 100088
SIGNUP = {"nome": "Ana", "sobrenome": "Silva", "email": "ana@x.com", "senha": "segredo123", "confirmacao": "segredo123"}


def visitor(make_client):
    return make_client(tracked_catalog(), user=None)


def set_cookies(response):
    return response.headers.get_list("set-cookie")


def test_sign_up_logs_in_and_goes_back(make_client):
    r = visitor(make_client).post("/criar-conta", data=SIGNUP | {"proximo": f"/serie/{ID}"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/serie/{ID}"
    assert any(h.startswith("op_acesso=tok-novo") for h in set_cookies(r))
    assert any(h.startswith("op_renovacao=ref-novo") for h in set_cookies(r))


def test_sign_up_validation_keeps_values_without_passwords(make_client):
    r = visitor(make_client).post("/criar-conta", data=SIGNUP | {"nome": ""})
    assert r.status_code == 200 and "Informe seu nome." in r.text
    assert 'value="ana@x.com"' in r.text and "segredo123" not in r.text
    assert 'aria-invalid="true" aria-describedby="erro-nome"' in r.text


def test_email_taken_offers_login(make_client):
    c = visitor(make_client)
    c.app.state.auth.error = EmailTaken()
    r = c.post("/criar-conta", data=SIGNUP)
    assert "Já existe uma conta com este e-mail." in r.text and 'href="/entrar' in r.text


def test_login_wrong_password(make_client):
    c = visitor(make_client)
    c.app.state.auth.accounts["eu@teste.com"] = ("certa-123", TEST_USER)
    r = c.post("/entrar", data={"email": "eu@teste.com", "senha": "errada-123"})
    assert r.status_code == 200 and "E-mail ou senha incorretos." in r.text


def test_login_goes_to_next_and_unsafe_next_goes_home(make_client):
    c = visitor(make_client)
    c.app.state.auth.accounts["eu@teste.com"] = ("certa-123", TEST_USER)
    ok = c.post("/entrar", data={"email": "eu@teste.com", "senha": "certa-123", "proximo": "/minhas-series"},
                follow_redirects=False)
    assert ok.headers["location"] == "/minhas-series"
    c.cookies.clear()
    evil = c.post("/entrar", data={"email": "eu@teste.com", "senha": "certa-123", "proximo": "//evil.com"},
                  follow_redirects=False)
    assert evil.headers["location"] == "/"


def test_login_page_keeps_next(make_client):
    assert 'name="proximo" value="/serie/1"' in visitor(make_client).get("/entrar?proximo=/serie/1").text


def test_logged_user_visiting_login_goes_home(make_client):
    for path in ("/entrar", "/criar-conta"):
        r = make_client(tracked_catalog()).get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"


def test_logout_clears_cookies(make_client):
    c = make_client(tracked_catalog())
    r = c.post("/sair", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cleared = {h.split("=")[0] for h in set_cookies(r) if "Max-Age=0" in h}
    assert cleared == {"op_acesso", "op_renovacao"}
    assert ("sign_out", ("tok-teste",)) in c.app.state.auth.calls


def test_forgot_password_always_same_message(make_client):
    c = visitor(make_client)
    message = "Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova."
    for email in ("eu@teste.com", "ninguem@x.com"):
        assert message in c.post("/esqueci-senha", data={"email": email}).text
    assert [args[0] for name, args in c.app.state.auth.calls if name == "recover"] == ["eu@teste.com", "ninguem@x.com"]


def test_recovery_link_expired(make_client):
    c = visitor(make_client)
    c.app.state.auth.error = InvalidRecoveryLink()
    r = c.get("/nova-senha?token_hash=velho&type=recovery")
    assert "Este link expirou." in r.text and 'href="/esqueci-senha"' in r.text and "Pedir outro link" in r.text


def test_new_password_flow(make_client):
    c = visitor(make_client)
    form = c.get("/nova-senha?token_hash=th&type=recovery")
    assert 'name="senha"' in form.text and c.cookies.get("op_acesso") == "tok-recuperacao"
    r = c.post("/nova-senha", data={"senha": "nova-senha-1", "confirmacao": "nova-senha-1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert ("update_password", ("tok-recuperacao",)) in c.app.state.auth.calls


def test_new_password_without_session_says_expired(make_client):
    r = visitor(make_client).post("/nova-senha", data={"senha": "nova-senha-1", "confirmacao": "nova-senha-1"})
    assert "Este link expirou." in r.text


def test_auth_unavailable_message_on_login(make_client):
    c = visitor(make_client)
    c.app.state.auth.error = AuthUnavailable()
    r = c.post("/entrar", data={"email": "eu@teste.com", "senha": "certa-123"})
    assert "Não foi possível falar com o servidor de contas. Tente novamente em instantes." in r.text


def test_header_visitor_links(make_client):
    t = visitor(make_client).get(f"/serie/{ID}").text.split("</header>")[0]
    assert f'href="/entrar?proximo=%2Fserie%2F{ID}"' in t and 'href="/criar-conta"' in t and "Criar conta" in t
    assert 'action="/sair"' not in t


def test_header_logged_shows_first_name_and_menu(make_client):
    t = make_client(tracked_catalog()).get(f"/serie/{ID}").text.split("</header>")[0]
    assert "Romany" in t and 'popovertarget="menu-usuario"' in t and 'action="/sair"' in t
    assert 'href="/minhas-series"' in t and 'href="/criar-conta"' not in t


def test_html_in_name_is_escaped(make_client):
    user = User("00000000-0000-0000-0000-000000000009", "x@x.com", "<b>Ro</b>", "M")
    t = make_client(tracked_catalog(), user=user).get(f"/serie/{ID}").text
    assert "&lt;b&gt;Ro&lt;/b&gt;" in t and "<b>Ro</b>" not in t


def test_confirmation_required_and_invalid_email_messages(make_client):
    from app.auth.client import ConfirmationRequired, InvalidEmail
    c = visitor(make_client)
    c.app.state.auth.error = ConfirmationRequired()
    assert "Conta criada. Confirme o e-mail que enviamos e depois entre." in c.post("/criar-conta", data=SIGNUP).text
    c.app.state.auth.error = InvalidEmail()
    assert "Informe um e-mail válido." in c.post("/criar-conta", data=SIGNUP).text


# Recuperação com o link padrão do Supabase (PKCE: ?code=...)
def test_forgot_password_starts_pkce(make_client):
    import base64
    import hashlib
    c = visitor(make_client)
    r = c.post("/esqueci-senha", data={"email": "eu@teste.com"})
    verifier = c.cookies.get("op_pkce")
    assert verifier and len(verifier) >= 43
    assert any(h.startswith("op_pkce=") and "HttpOnly" in h for h in r.headers.get_list("set-cookie"))
    (_, (email, redirect_to, challenge)), = [c_ for c_ in c.app.state.auth.calls if c_[0] == "recover"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert (email, redirect_to, challenge) == ("eu@teste.com", "http://testserver/nova-senha", expected)


def test_recovery_code_is_exchanged_with_the_cookie_verifier(make_client):
    c = visitor(make_client)
    c.post("/esqueci-senha", data={"email": "eu@teste.com"})
    verifier = c.cookies.get("op_pkce")
    form = c.get("/nova-senha?code=abc")
    assert 'name="senha"' in form.text and c.cookies.get("op_acesso") == "tok-recuperacao"
    assert ("exchange_code", ("abc", verifier)) in c.app.state.auth.calls


def test_recovery_code_without_verifier_cookie_is_expired(make_client):
    c = visitor(make_client)
    r = c.get("/nova-senha?code=abc")
    assert "Este link expirou." in r.text
    assert not any(name == "exchange_code" for name, _ in c.app.state.auth.calls)


def _eye_buttons(html):
    return html.count('class="campo-olho"')


def test_every_password_field_has_an_eye_and_email_does_not(make_client):
    c = visitor(make_client)
    login = c.get("/entrar").text
    assert _eye_buttons(login) == 1
    assert _eye_buttons(c.get("/criar-conta").text) == 2
    assert _eye_buttons(c.get("/nova-senha?token_hash=th&type=recovery").text) == 2
    assert _eye_buttons(c.get("/esqueci-senha").text) == 0
    eye = login.split('class="campo-olho"')[0].rsplit("<button", 1)[1] + login.split('class="campo-olho"')[1].split(">")[0]
    assert 'type="button"' in eye and 'aria-label="Mostrar senha"' in eye and 'aria-pressed="false"' in eye
