"""Páginas de conta: entrar, criar conta, sair, esqueci minha senha e nova senha."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.auth.client import (AuthError, AuthUnavailable, EmailTaken, InvalidCredentials, InvalidRecoveryLink,
                             InvalidSession, RateLimited, WeakPassword)
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
    RateLimited: RATE_LIMITED,
    AuthUnavailable: UNAVAILABLE,
}
_SECRET_FIELDS = {"senha", "confirmacao"}


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
    try:
        await request.app.state.auth.recover(email)
    except (RateLimited, AuthUnavailable) as exc:
        return _render(request, "esqueci_senha.html", valores=_values(form), erro_geral=_message(exc))
    except AuthError:
        pass  # mesma resposta para todos: não revela quem tem conta
    return _render(request, "esqueci_senha.html", enviado=RECOVERY_SENT)


@router.get("/nova-senha")
async def new_password_page(request: Request):
    token_hash = request.query_params.get("token_hash")
    if not token_hash or request.query_params.get("type") != "recovery":
        return _render(request, "nova_senha.html", expirado=True)
    try:
        session = await request.app.state.auth.verify_recovery(token_hash)
    except InvalidRecoveryLink:
        return _render(request, "nova_senha.html", expirado=True)
    except AuthError as exc:
        return _render(request, "nova_senha.html", expirado=True, erro_geral=_message(exc))
    response = _render(request, "nova_senha.html")
    set_session_cookies(response, session, secure=request.url.scheme == "https")
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
