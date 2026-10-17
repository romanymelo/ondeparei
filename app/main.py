import logging
import sqlite3
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
from app.tracking.db import connect
from app.tracking.repository import TrackingRepository
from app.tracking.routes import router as tracking_router
from app.tracking.service import InvalidAction, TrackingService
from app.templating import APP_NAME, VARY_HX, is_htmx, templates
from app.tmdb.cache import TTLCache
from app.tmdb.client import TMDBAuthError, TMDBClient, TMDBNotFound, TMDBUnavailable, create_http_client

STATIC_DIR = Path(__file__).parent / "static"
SAVE_ERROR = "Não foi possível salvar sua marcação. Tente novamente."

logger = logging.getLogger(__name__)


def _retry_path(request: Request) -> str:
    """URL relativa para "Tentar novamente": a página que o navegador mostra, não o fragmento pedido."""
    parts = urlsplit(request.headers.get("HX-Current-URL") or str(request.url))
    path = parts.path if parts.path.startswith("/") and not parts.path.startswith("//") else "/"
    return f"{path}?{parts.query}" if parts.query else path


def _error_response(request: Request, status: int, message: str, retry: bool, htmx_status: int = 200):
    context = {"message": message, "retry_url": _retry_path(request) if retry else None}
    if is_htmx(request):
        return templates.TemplateResponse(request, "_erro.html", context, status_code=htmx_status, headers=VARY_HX)
    return templates.TemplateResponse(request, "erro.html", context, status_code=status, headers=VARY_HX)


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

    @app.exception_handler(InvalidAction)
    async def invalid_action(request: Request, exc: InvalidAction):
        # 400 também com HTMX: o HTMX não troca o conteúdo em 4xx, então a tela fica como estava
        return _error_response(request, 400, "Ação inválida", retry=False, htmx_status=400)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error):
        logger.error("Falha ao gravar a marcação no banco: %s", exc)
        return _error_response(request, 500, SAVE_ERROR, retry=False)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _error_response(request, 404, "Página não encontrada", retry=False)
        return await http_exception_handler(request, exc)


def _start_tracking(app: FastAPI, catalog, database_path: str | Path):
    conn = connect(database_path)
    app.state.tracking = TrackingService(catalog, TrackingRepository(conn))
    return conn


def create_app(settings: Settings | None = None, catalog: Catalog | None = None,
               database_path: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if catalog is not None:
            app.state.catalog = catalog
            conn = _start_tracking(app, catalog, database_path or ":memory:")
            try:
                yield
            finally:
                conn.close()
            return
        try:
            config = settings or load_settings()
        except ConfigError as exc:
            logger.error("%s", exc)
            raise
        logging.basicConfig(level=config.log_level.upper())
        http = create_http_client(config.tmdb_token.get_secret_value())
        app.state.catalog = Catalog(TMDBClient(http, TTLCache()), config.tmdb_region, config.tmdb_language)
        conn = _start_tracking(app, app.state.catalog, database_path or config.database_path)
        try:
            yield
        finally:
            conn.close()
            await http.aclose()

    app = FastAPI(title=APP_NAME, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    app.include_router(tracking_router)
    _register_error_handlers(app)
    return app


app = create_app()
