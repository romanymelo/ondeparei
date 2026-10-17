from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.filters import RATINGS
from app.mappers import WATCH_TYPE_LABELS
from app.models import ALL_TYPES

APP_NAME = "SériesBR"
SORT_LABELS = {
    "popularidade": "Popularidade",
    "nota": "Nota",
    "recentes": "Mais recentes",
    "nome": "Nome A–Z",
}
VISIBLE_PROVIDERS = 12
TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def format_thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_rating(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


VARY_HX = {"Vary": "HX-Request"}


def is_htmx(request: Request) -> bool:
    """Pedido de fragmento do HTMX. Restauração de histórico pede a página inteira."""
    return (request.headers.get("HX-Request") == "true"
            and request.headers.get("HX-History-Restore-Request") != "true")


templates.env.globals.update(
    APP_NAME=APP_NAME,
    WATCH_TYPE_LABELS=WATCH_TYPE_LABELS,
    SORT_LABELS=SORT_LABELS,
    RATINGS=RATINGS,
    ALL_TYPES=ALL_TYPES,
    VISIBLE_PROVIDERS=VISIBLE_PROVIDERS,
)
templates.env.filters.update(milhar=format_thousands, nota=format_rating)
