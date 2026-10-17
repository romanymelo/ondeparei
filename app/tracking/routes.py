"""Rotas das marcações: ações POST, página da temporada e Minhas séries."""

from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException

from app.auth.session import LoginRequired
from app.navigation import remember_list
from app.templating import NO_STORE, VARY_HX, is_htmx, templates
from app.tmdb.client import TMDBNotFound
from app.tracking.service import InvalidAction, TrackingService
from app.tracking.store import ReadSafeStore, TrackingUnavailable, VisitorStore

router = APIRouter()


def get_tracking(request: Request) -> TrackingService:
    """Marcações da pessoa logada; visitante é levado ao login."""
    user = getattr(request.state, "user", None)
    if user is None:
        if getattr(request.state, "auth_unavailable", False):
            raise TrackingUnavailable("Supabase Auth fora do ar")  # não é caso de pedir login
        raise LoginRequired()
    stores = getattr(request.app.state, "stores", None)
    if stores is None:
        raise TrackingUnavailable("sem banco de marcações configurado")
    return TrackingService(request.app.state.catalog, stores(user, request.state.access_token))


def page_tracking(request: Request) -> TrackingService:
    """Para páginas que qualquer um abre: visitante vê tudo desmarcado."""
    user = getattr(request.state, "user", None)
    stores = getattr(request.app.state, "stores", None)
    if user is None or stores is None:
        return TrackingService(request.app.state.catalog, VisitorStore())
    # se o banco das marcações cair, a página abre como para visitante (o catálogo continua navegável)
    return TrackingService(request.app.state.catalog, ReadSafeStore(stores(user, request.state.access_token)))


async def read_form(request: Request) -> dict[str, str]:
    """Corpo application/x-www-form-urlencoded, primeiro valor de cada campo (sem python-multipart)."""
    body = (await request.body()).decode("utf-8", errors="replace")
    return {key: values[0] for key, values in parse_qs(body).items()}


def int_field(form: dict[str, str], name: str) -> int:
    value = form.get(name, "")
    if not (value.isascii() and value.isdigit()):  # recusa ausente, negativo, decimal, texto e "²"
        raise InvalidAction(f"{name}={value!r}")
    return int(value)


def _status_response(request: Request, series_id: int, tracking):
    if is_htmx(request):
        return templates.TemplateResponse(request, "_status.html", {"series_id": series_id, "tracking": tracking},
                                          headers=VARY_HX)
    return RedirectResponse(f"/serie/{series_id}", status_code=303)


@router.post("/serie/{series_id:int}/status")
async def set_status(request: Request, series_id: int, background: BackgroundTasks,
                     tracking: TrackingService = Depends(get_tracking)):
    form = await read_form(request)
    result = await tracking.set_status(series_id, form.get("status", ""))
    background.add_task(tracking.fill_runtimes)  # "Assistido" marca episódios sem duração: busca logo depois
    return _status_response(request, series_id, result)


@router.post("/serie/{series_id:int}/favorito")
async def toggle_favorite(request: Request, series_id: int, tracking: TrackingService = Depends(get_tracking)):
    return _status_response(request, series_id, await tracking.toggle_favorite(series_id))


@router.get("/serie/{series_id:int}/temporada/{number:int}")
async def season_page(request: Request, series_id: int, number: int,
                      tracking: TrackingService = Depends(page_tracking)):
    try:
        view = await tracking.season(series_id, number)
    except TMDBNotFound:
        raise HTTPException(status_code=404) from None
    return templates.TemplateResponse(request, "temporada.html", {"view": view}, headers=VARY_HX | NO_STORE)


def _season_response(request: Request, series_id: int, season: int, view):
    if is_htmx(request):
        return templates.TemplateResponse(request, "_temporada.html", {"view": view}, headers=VARY_HX)
    return RedirectResponse(f"/serie/{series_id}/temporada/{season}", status_code=303)


@router.post("/serie/{series_id:int}/episodio")
async def toggle_episode(request: Request, series_id: int, tracking: TrackingService = Depends(get_tracking)):
    form = await read_form(request)
    season, episode = int_field(form, "temporada"), int_field(form, "episodio")
    return _season_response(request, series_id, season, await tracking.toggle_episode(series_id, season, episode))


@router.post("/serie/{series_id:int}/ate-aqui")
async def mark_up_to(request: Request, series_id: int, background: BackgroundTasks,
                     tracking: TrackingService = Depends(get_tracking)):
    form = await read_form(request)
    season, episode = int_field(form, "temporada"), int_field(form, "episodio")
    background.add_task(tracking.fill_runtimes)  # temporadas anteriores ficam sem duração: busca logo depois
    return _season_response(request, series_id, season, await tracking.mark_up_to(series_id, season, episode))


@router.post("/serie/{series_id:int}/temporada/{number:int}/toda")
async def toggle_season(request: Request, series_id: int, number: int,
                        tracking: TrackingService = Depends(get_tracking)):
    return _season_response(request, series_id, number, await tracking.toggle_season(series_id, number))


@router.get("/minhas-series")
async def my_series_page(request: Request, tracking: TrackingService = Depends(get_tracking)):
    view = await tracking.my_series(request.query_params.get("aba", ""))
    response = templates.TemplateResponse(request, "minhas_series.html", {"view": view}, headers=VARY_HX | NO_STORE)
    return remember_list(request, response)
