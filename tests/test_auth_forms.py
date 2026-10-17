import pytest

from app.auth.forms import SignupData, safe_next, validate_login, validate_new_password, validate_signup


@pytest.mark.parametrize("value", [None, "", "//evil.com", "/\\evil.com", "https://evil.com", "evil.com", "javascript:x"])
def test_safe_next_rejects_outside(value):
    assert safe_next(value) == "/"


def test_safe_next_keeps_local_path():
    assert safe_next("/serie/1?aba=x") == "/serie/1?aba=x"


def test_signup_ok_strips_and_lowercases():
    data, errors = validate_signup({"nome": " Romany ", "sobrenome": "Melo", "email": " Eu@X.com ",
                                    "senha": "segredo123", "confirmacao": "segredo123"})
    assert errors == {} and data == SignupData("Romany", "Melo", "eu@x.com", "segredo123")


def test_signup_errors():
    data, errors = validate_signup({"nome": "", "sobrenome": "x" * 61, "email": "eu@", "senha": "curta",
                                    "confirmacao": "outra"})
    assert data is None
    assert errors == {"nome": "Informe seu nome.", "sobrenome": "Use até 60 caracteres.",
                      "email": "Informe um e-mail válido.", "senha": "A senha precisa ter pelo menos 8 caracteres.",
                      "confirmacao": "As senhas não são iguais."}


def test_signup_missing_fields():
    _, errors = validate_signup({})
    assert errors["nome"] == "Informe seu nome." and errors["sobrenome"] == "Informe seu sobrenome."


def test_login_requires_email_and_password():
    assert validate_login({}) == (None, {"email": "Informe um e-mail válido.", "senha": "Informe sua senha."})
    assert validate_login({"email": " Eu@X.com", "senha": "x"}) == (("eu@x.com", "x"), {})


def test_new_password():
    assert validate_new_password({"senha": "curta", "confirmacao": "curta"}) == (
        None, {"senha": "A senha precisa ter pelo menos 8 caracteres."})
    assert validate_new_password({"senha": "segredo123", "confirmacao": "outra"}) == (
        None, {"confirmacao": "As senhas não são iguais."})
    assert validate_new_password({"senha": "segredo123", "confirmacao": "segredo123"}) == ("segredo123", {})
