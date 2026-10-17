"""Rotas das marcações: ações POST, página da temporada e Minhas séries."""

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException

from app.navigation import remember_list
from app.templating import NO_STORE, VARY_HX, is_htmx, templates
from app.tmdb.client import TMDBNotFound
from app.tracking.service import InvalidAction, TrackingService

router = APIRouter()


def get_tracking(request: Request) -> TrackingService:
    return request.app.state.tracking


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
async def set_status(request: Request, series_id: int, tracking: TrackingService = Depends(get_tracking)):
    form = await read_form(request)
    result = await tracking.set_status(series_id, form.get("status", ""))
    return _status_response(request, series_id, result)


@router.post("/serie/{series_id:int}/favorito")
async def toggle_favorite(request: Request, series_id: int, tracking: TrackingService = Depends(get_tracking)):
    return _status_response(request, series_id, await tracking.toggle_favorite(series_id))


@router.get("/serie/{series_id:int}/temporada/{number:int}")
async def season_page(request: Request, series_id: int, number: int, tracking: TrackingService = Depends(get_tracking)):
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
async def mark_up_to(request: Request, series_id: int, tracking: TrackingService = Depends(get_tracking)):
    form = await read_form(request)
    season, episode = int_field(form, "temporada"), int_field(form, "episodio")
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
