from collections.abc import Awaitable, Sequence
from typing import TypeVar
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.catalog import Catalog
from app.filters import parse_filters, parse_page
from app.models import Provider
from app.templating import VARY_HX, VISIBLE_PROVIDERS, is_htmx, templates
from app.tmdb.client import TMDBError

router = APIRouter()

T = TypeVar("T")


def get_catalog(request: Request) -> Catalog:
    return request.app.state.catalog


def query_dict(request: Request) -> dict[str, list[str]]:
    query: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        query.setdefault(key, []).append(value)
    return query


def next_page_url(path: str, query_items: Sequence[tuple[str, str]], next_page: int) -> str:
    items = [(k, v) for k, v in query_items if k != "pagina"] + [("pagina", str(next_page))]
    return f"{path}?{urlencode(items)}"


async def _or_none(call: Awaitable[T]) -> T | None:
    """Listas auxiliares (serviços, gêneros) não derrubam a página quando a TMDB falha."""
    try:
        return await call
    except TMDBError:
        return None


def split_providers(providers: Sequence[Provider], selected: Sequence[int],
                    limit: int = VISIBLE_PROVIDERS) -> tuple[list[Provider], list[Provider]]:
    """Os `limit` primeiros ficam na faixa visível, mais qualquer serviço selecionado que estaria escondido."""
    visible = [p for i, p in enumerate(providers) if i < limit or p.id in selected]
    rest = [p for i, p in enumerate(providers) if i >= limit and p.id not in selected]
    return visible, rest


@router.get("/")
async def catalog_page(request: Request, catalog: Catalog = Depends(get_catalog)):
    filters = parse_filters(query_dict(request))
    page = await catalog.discover(filters)
    context = {
        "filters": filters,
        "page": page,
        "has_next": page.page < page.total_pages,
        "next_url": next_page_url(request.url.path, request.query_params.multi_items(), page.page + 1),
    }
    if is_htmx(request):
        template = "_cartoes.html" if filters.page > 1 else "_grade.html"
        return templates.TemplateResponse(request, template, context | {"oob": True}, headers=VARY_HX)

    providers = await _or_none(catalog.providers())
    visible, rest = split_providers(providers or (), filters.providers)
    context |= {
        "providers": providers,
        "visible_providers": visible,
        "more_providers": rest,
        "genres": await _or_none(catalog.genres()),
        "spotlight": await _or_none(catalog.spotlight()),
    }
    return templates.TemplateResponse(request, "catalogo.html", context, headers=VARY_HX)


@router.get("/buscar")
async def search_page(request: Request, catalog: Catalog = Depends(get_catalog)):
    q = request.query_params.get("q", "").strip()
    if not q:
        return RedirectResponse("/", status_code=303)
    page_number = parse_page(request.query_params.getlist("pagina"))
    page = await catalog.search(q, page_number)
    context = {
        "q": q,
        "page": page,
        "has_next": page.page < page.total_pages,
        "next_url": next_page_url(request.url.path, request.query_params.multi_items(), page.page + 1),
    }
    if is_htmx(request) and page_number > 1:
        return templates.TemplateResponse(request, "_cartoes.html", context, headers=VARY_HX)
    return templates.TemplateResponse(request, "busca.html", context, headers=VARY_HX)


@router.get("/serie/{series_id:int}")
async def series_page(request: Request, series_id: int, catalog: Catalog = Depends(get_catalog)):
    serie = await catalog.detail(series_id)
    return templates.TemplateResponse(request, "serie.html", {"serie": serie})
