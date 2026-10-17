"""Validação pura dos formulários de conta. Erros por campo, com o texto que aparece na tela."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_NAME = 60
MIN_PASSWORD = 8


@dataclass(frozen=True)
class SignupData:
    first_name: str
    last_name: str
    email: str
    password: str


def safe_next(value: str | None) -> str:
    """Destino depois do login: só caminho do próprio site; qualquer outra coisa vira "/"."""
    if not value or not value.startswith("/") or value.startswith(("//", "/\\")):
        return "/"
    return value


def _name(form: Mapping[str, str], field: str, missing: str, errors: dict[str, str]) -> str:
    value = (form.get(field) or "").strip()
    if not value:
        errors[field] = missing
    elif len(value) > MAX_NAME:
        errors[field] = "Use até 60 caracteres."
    return value


def _email(form: Mapping[str, str], errors: dict[str, str]) -> str:
    value = (form.get("email") or "").strip().lower()
    if not EMAIL_RE.match(value):
        errors["email"] = "Informe um e-mail válido."
    return value


def _new_password(form: Mapping[str, str], errors: dict[str, str]) -> str:
    password = form.get("senha") or ""
    if len(password) < MIN_PASSWORD:
        errors["senha"] = "A senha precisa ter pelo menos 8 caracteres."
    elif form.get("confirmacao") != password:
        errors["confirmacao"] = "As senhas não são iguais."
    return password


def validate_signup(form: Mapping[str, str]) -> tuple[SignupData | None, dict[str, str]]:
    errors: dict[str, str] = {}
    first = _name(form, "nome", "Informe seu nome.", errors)
    last = _name(form, "sobrenome", "Informe seu sobrenome.", errors)
    email = _email(form, errors)
    password = form.get("senha") or ""
    if len(password) < MIN_PASSWORD:
        errors["senha"] = "A senha precisa ter pelo menos 8 caracteres."
    if form.get("confirmacao") != password:
        errors["confirmacao"] = "As senhas não são iguais."
    return (None if errors else SignupData(first, last, email, password)), errors


def validate_login(form: Mapping[str, str]) -> tuple[tuple[str, str] | None, dict[str, str]]:
    errors: dict[str, str] = {}
    email = _email(form, errors)
    password = form.get("senha") or ""
    if not password:
        errors["senha"] = "Informe sua senha."
    return (None if errors else (email, password)), errors


def validate_new_password(form: Mapping[str, str]) -> tuple[str | None, dict[str, str]]:
    errors: dict[str, str] = {}
    password = _new_password(form, errors)
    return (None if errors else password), errors
