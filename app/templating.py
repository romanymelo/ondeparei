from datetime import date
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.filters import RATINGS
from app.mappers import WATCH_TYPE_LABELS, watch_services

APP_NAME = "OndeParei"
SORT_LABELS = {
    "popularidade": "Popularidade",
    "nota": "Nota",
    "recentes": "Mais recentes",
    "nome": "Nome A–Z",
}
VISIBLE_PROVIDERS = 6
# os maiores do Brasil, na faixa visível nesta ordem: Netflix, Prime Video, Disney+, HBO Max, Globoplay, Paramount+.
# A ordem da TMDB põe JustWatch TV e Claro video entre os primeiros, por isso a lista fixa.
POPULAR_PROVIDERS = (8, 119, 337, 1899, 307, 531)
TAB_LABELS = {"assistindo": "Assistindo", "quero": "Quero assistir", "assistidas": "Assistidas", "favoritas": "Favoritas"}
TAB_ICONS = {"assistindo": "watching", "quero": "want", "assistidas": "watched", "favoritas": "favorite"}
MARK_LABELS = {"want": "Quero assistir", "watching": "Assistindo", "watched": "Assistido", "favorite": "Favorita"}
TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def format_thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_rating(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def format_percent(pair: tuple[int, int]) -> str:
    """(feitos, total) -> "33%"; total zero dá "0%"."""
    done, total = pair
    return f"{round(100 * done / total) if total else 0}%"


def format_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_episode(episode: tuple[int, int]) -> str:
    return f"T{episode[0]}E{episode[1]}"


VARY_HX = {"Vary": "HX-Request"}
# páginas com marcações: o Voltar do navegador não pode mostrar uma cópia antiga
NO_STORE = {"Cache-Control": "no-store"}


def is_htmx(request: Request) -> bool:
    """Pedido de fragmento do HTMX. Restauração de histórico pede a página inteira."""
    return (request.headers.get("HX-Request") == "true"
            and request.headers.get("HX-History-Restore-Request") != "true")


templates.env.globals.update(
    APP_NAME=APP_NAME,
    WATCH_TYPE_LABELS=WATCH_TYPE_LABELS,
    SORT_LABELS=SORT_LABELS,
    RATINGS=RATINGS,
    VISIBLE_PROVIDERS=VISIBLE_PROVIDERS,
    MARK_LABELS=MARK_LABELS,
    TAB_LABELS=TAB_LABELS,
    TAB_ICONS=TAB_ICONS,
)
templates.env.filters.update(milhar=format_thousands, nota=format_rating, servicos=watch_services,
                             porcento=format_percent, ep=format_episode,
                             data=format_date)
