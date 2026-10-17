from collections.abc import Awaitable, Sequence
from datetime import date
from typing import TypeVar
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.catalog import Catalog
from app.filters import parse_filters, parse_page
from app.templating import is_htmx, templates
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


@router.get("/")
async def catalog_page(request: Request, catalog: Catalog = Depends(get_catalog)):
    current_year = date.today().year
    filters = parse_filters(query_dict(request), current_year)
    page = await catalog.discover(filters)
    context = {
        "filters": filters,
        "page": page,
        "has_next": page.page < page.total_pages,
        "next_url": next_page_url(request.url.path, request.query_params.multi_items(), page.page + 1),
    }
    if is_htmx(request):
        template = "_cartoes.html" if filters.page > 1 else "_grade.html"
        return templates.TemplateResponse(request, template, context | {"oob": True})

    context |= {
        "providers": await _or_none(catalog.providers()),
        "genres": await _or_none(catalog.genres()),
        "current_year": current_year,
    }
    return templates.TemplateResponse(request, "catalogo.html", context)


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
        return templates.TemplateResponse(request, "_cartoes.html", context)
    return templates.TemplateResponse(request, "busca.html", context)
