"""Rotas das marcações: ações POST, página da temporada e Minhas séries."""

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.templating import VARY_HX, is_htmx, templates
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
    if not value.isdigit():  # recusa ausente, negativo, decimal e texto
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
