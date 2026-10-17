from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.mappers import WATCH_TYPE_LABELS

APP_NAME = "SériesBR"
TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def format_thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_rating(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


templates.env.globals.update(APP_NAME=APP_NAME, WATCH_TYPE_LABELS=WATCH_TYPE_LABELS)
templates.env.filters.update(milhar=format_thousands, nota=format_rating)
