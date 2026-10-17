"""Páginas de conta: entrar, criar conta, sair, esqueci minha senha e nova senha."""

import base64
import hashlib
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.auth.client import (AuthError, AuthUnavailable, ConfirmationRequired, EmailTaken, InvalidCredentials,
                             InvalidEmail, InvalidRecoveryLink, InvalidSession, RateLimited, SamePassword,
                             WeakPassword)
from app.auth.forms import safe_next, validate_login, validate_new_password, validate_signup
from app.auth.session import clear_session_cookies, set_session_cookies
from app.templating import NO_STORE, templates
from app.tracking.routes import read_form

router = APIRouter()

UNAVAILABLE = "Não foi possível falar com o servidor de contas. Tente novamente em instantes."
RATE_LIMITED = "Muitas tentativas. Aguarde um minuto e tente de novo."
RECOVERY_SENT = "Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova."
_MESSAGES = {
    InvalidCredentials: "E-mail ou senha incorretos.",
    EmailTaken: "Já existe uma conta com este e-mail.",
    WeakPassword: "Use uma senha mais forte (mínimo de 8 caracteres).",
    ConfirmationRequired: "Conta criada. Confirme o e-mail que enviamos e depois entre.",
    InvalidEmail: "Informe um e-mail válido.",
    SamePassword: "Use uma senha diferente da atual.",
    RateLimited: RATE_LIMITED,
    AuthUnavailable: UNAVAILABLE,
}
_SECRET_FIELDS = {"senha", "confirmacao"}
PKCE_COOKIE = "op_pkce"
PKCE_MAX_AGE = 3600  # o link de recuperação do Supabase vale 1 hora


def _pkce_pair() -> tuple[str, str]:
    """(verifier, challenge S256) do PKCE: o verifier fica num cookie deste navegador."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _message(exc: AuthError) -> str:
    return next((text for kind, text in _MESSAGES.items() if isinstance(exc, kind)), UNAVAILABLE)


def _render(request: Request, template: str, **context):
    return templates.TemplateResponse(request, template, {"valores": {}, "erros": {}} | context, headers=NO_STORE)


def _values(form: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in form.items() if k not in _SECRET_FIELDS}


def _logged_in(request: Request) -> RedirectResponse:
    return RedirectResponse("/", status_code=303)


def _signed_in(request: Request, session, destination: str) -> RedirectResponse:
    response = RedirectResponse(destination, status_code=303)
    set_session_cookies(response, session, secure=request.url.scheme == "https")
    request.state.session_written = True
    return response


@router.get("/entrar")
async def login_page(request: Request):
    if request.state.user is not None:
        return _logged_in(request)
    return _render(request, "entrar.html", proximo=safe_next(request.query_params.get("proximo")))


@router.post("/entrar")
async def login(request: Request):
    form = await read_form(request)
    proximo = safe_next(form.get("proximo"))
    credentials, errors = validate_login(form)
    if credentials is None:
        return _render(request, "entrar.html", proximo=proximo, valores=_values(form), erros=errors)
    try:
        session = await request.app.state.auth.sign_in(*credentials)
    except AuthError as exc:
        return _render(request, "entrar.html", proximo=proximo, valores=_values(form), erro_geral=_message(exc))
    return _signed_in(request, session, proximo)


@router.get("/criar-conta")
async def signup_page(request: Request):
    if request.state.user is not None:
        return _logged_in(request)
    return _render(request, "criar_conta.html", proximo=safe_next(request.query_params.get("proximo")))


@router.post("/criar-conta")
async def signup(request: Request):
    form = await read_form(request)
    proximo = safe_next(form.get("proximo"))
    data, errors = validate_signup(form)
    if data is None:
        return _render(request, "criar_conta.html", proximo=proximo, valores=_values(form), erros=errors)
    try:
        session = await request.app.state.auth.sign_up(data.email, data.password, data.first_name, data.last_name)
    except AuthError as exc:
        return _render(request, "criar_conta.html", proximo=proximo, valores=_values(form),
                       erro_geral=_message(exc), email_em_uso=isinstance(exc, EmailTaken))
    return _signed_in(request, session, proximo)


@router.post("/sair")
async def logout(request: Request):
    token = request.state.access_token
    if token:
        try:
            await request.app.state.auth.sign_out(token)
        except AuthError:
            pass  # sai deste navegador de qualquer jeito
    response = RedirectResponse("/", status_code=303)
    clear_session_cookies(response)
    request.state.session_written = True
    return response


@router.get("/esqueci-senha")
async def forgot_page(request: Request):
    return _render(request, "esqueci_senha.html")


@router.post("/esqueci-senha")
async def forgot(request: Request):
    form = await read_form(request)
    email = (form.get("email") or "").strip().lower()
    _, errors = validate_login({"email": email, "senha": "-"})
    if errors:
        return _render(request, "esqueci_senha.html", valores=_values(form), erros=errors)
    verifier, challenge = _pkce_pair()
    redirect_to = f"{str(request.base_url).rstrip('/')}/nova-senha"
    try:
        await request.app.state.auth.recover(email, redirect_to=redirect_to, code_challenge=challenge)
    except (RateLimited, AuthUnavailable) as exc:
        return _render(request, "esqueci_senha.html", valores=_values(form), erro_geral=_message(exc))
    except AuthError:
        pass  # mesma resposta para todos: não revela quem tem conta
    response = _render(request, "esqueci_senha.html", enviado=RECOVERY_SENT)
    response.set_cookie(PKCE_COOKIE, verifier, max_age=PKCE_MAX_AGE, httponly=True, samesite="lax", path="/",
                        secure=request.url.scheme == "https")
    return response


@router.get("/nova-senha")
async def new_password_page(request: Request):
    code = request.query_params.get("code")
    token_hash = request.query_params.get("token_hash")
    try:
        if code:  # link padrão do Supabase (PKCE): precisa do verifier guardado neste navegador
            verifier = request.cookies.get(PKCE_COOKIE)
            if not verifier:
                return _render(request, "nova_senha.html", expirado=True)
            session = await request.app.state.auth.exchange_code(code, verifier)
        elif token_hash and request.query_params.get("type") == "recovery":  # modelo de e-mail próprio (SMTP)
            session = await request.app.state.auth.verify_recovery(token_hash)
        else:
            return _render(request, "nova_senha.html", expirado=True)
    except InvalidRecoveryLink:
        return _render(request, "nova_senha.html", expirado=True)
    except AuthError as exc:
        return _render(request, "nova_senha.html", expirado=True, erro_geral=_message(exc))
    response = _render(request, "nova_senha.html")
    set_session_cookies(response, session, secure=request.url.scheme == "https")
    response.delete_cookie(PKCE_COOKIE, path="/")
    request.state.session_written = True
    return response


@router.post("/nova-senha")
async def new_password(request: Request):
    if request.state.user is None:
        return _render(request, "nova_senha.html", expirado=True)
    form = await read_form(request)
    password, errors = validate_new_password(form)
    if password is None:
        return _render(request, "nova_senha.html", erros=errors)
    try:
        await request.app.state.auth.update_password(request.state.access_token, password)
    except InvalidSession:
        return _render(request, "nova_senha.html", expirado=True)
    except AuthError as exc:
        return _render(request, "nova_senha.html", erro_geral=_message(exc))
    return RedirectResponse("/", status_code=303)
