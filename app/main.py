import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.catalog import Catalog
from app.config import ConfigError, Settings, load_settings
from app.routes import router
from app.templating import APP_NAME, is_htmx, templates
from app.tmdb.cache import TTLCache
from app.tmdb.client import TMDBAuthError, TMDBClient, TMDBNotFound, TMDBUnavailable, create_http_client

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)


def _retry_path(request: Request) -> str:
    """URL relativa para "Tentar novamente": a página que o navegador mostra, não o fragmento pedido."""
    parts = urlsplit(request.headers.get("HX-Current-URL") or str(request.url))
    path = parts.path if parts.path.startswith("/") and not parts.path.startswith("//") else "/"
    return f"{path}?{parts.query}" if parts.query else path


def _error_response(request: Request, status: int, message: str, retry: bool):
    context = {"message": message, "retry_url": _retry_path(request) if retry else None}
    if is_htmx(request):
        return templates.TemplateResponse(request, "_erro.html", context, status_code=200)
    return templates.TemplateResponse(request, "erro.html", context, status_code=status)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TMDBNotFound)
    async def not_found(request: Request, exc: TMDBNotFound):
        return _error_response(request, 404, "Série não encontrada", retry=False)

    @app.exception_handler(TMDBAuthError)
    async def auth_error(request: Request, exc: TMDBAuthError):
        logger.error("A TMDB recusou o token (401). Confira TMDB_TOKEN no .env.")
        return _error_response(request, 502, "Problema de configuração com a TMDB (token inválido)", retry=False)

    @app.exception_handler(TMDBUnavailable)
    async def unavailable(request: Request, exc: TMDBUnavailable):
        logger.warning("TMDB indisponível: %s", exc)
        return _error_response(request, 503, "A TMDB não respondeu. Tente novamente em instantes.", retry=True)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _error_response(request, 404, "Página não encontrada", retry=False)
        return await http_exception_handler(request, exc)


def create_app(settings: Settings | None = None, catalog: Catalog | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if catalog is not None:
            app.state.catalog = catalog
            yield
            return
        try:
            config = settings or load_settings()
        except ConfigError as exc:
            logger.error("%s", exc)
            raise
        logging.basicConfig(level=config.log_level.upper())
        http = create_http_client(config.tmdb_token.get_secret_value())
        app.state.catalog = Catalog(TMDBClient(http, TTLCache()), config.tmdb_region, config.tmdb_language)
        try:
            yield
        finally:
            await http.aclose()

    app = FastAPI(title=APP_NAME, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    _register_error_handlers(app)
    return app


app = create_app()
