from datetime import date
from urllib.parse import quote
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
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def format_thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_rating(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def format_percent(pair: tuple[int, int]) -> str:
    """(feitos, total) -> "33%"; total zero dá "0%"."""
    done, total = pair
    return f"{round(100 * done / total) if total else 0}%"


def watch_time_parts(minutes: int) -> tuple[int, int, int]:
    """(meses, dias, horas) assistidos, como no TV Time: mês = 30 dias, minutos que sobram não contam."""
    months, hours = divmod(minutes // 60, 30 * 24)
    days, hours = divmod(hours, 24)
    return months, days, hours


_UNITS = (("mês", "meses"), ("dia", "dias"), ("hora", "horas"))


def watch_time_units(minutes: int) -> list[tuple[int, str]]:
    """Unidades do contador do cabeçalho, a partir da primeira não nula (horas sempre aparecem)."""
    parts = list(zip(watch_time_parts(minutes), _UNITS))
    first = next((i for i, (value, _) in enumerate(parts) if value), len(parts) - 1)
    return [(value, singular if value == 1 else plural) for value, (singular, plural) in parts[first:]]


def format_watch_time(minutes: int) -> str:
    """Tempo assistido como no TV Time: "2 meses 5 dias 7 horas" (só as unidades não nulas)."""
    months, days, hours = watch_time_parts(minutes)
    parts = [f"{n} {singular if n == 1 else plural}"
             for n, singular, plural in ((months, "mês", "meses"), (days, "dia", "dias"), (hours, "hora", "horas"))
             if n]
    return " ".join(parts) or "0 horas"


def format_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_episode(episode: tuple[int, int]) -> str:
    return f"T{episode[0]}E{episode[1]}"


def static_url(name: str) -> str:
    """URL de um arquivo estático com a data de modificação: mudou o arquivo, o navegador busca de novo."""
    return f"/static/{name}?v={int((STATIC_DIR / name).stat().st_mtime)}"


ACCOUNT_PAGES = ("/entrar", "/criar-conta", "/esqueci-senha", "/nova-senha")


def login_url(request: Request) -> str:
    """Link "Entrar" do cabeçalho, voltando para a página atual depois do login."""
    path = request.url.path
    if path.startswith(ACCOUNT_PAGES):
        return "/entrar"
    here = f"{path}?{request.url.query}" if request.url.query else path
    return f"/entrar?proximo={quote(here, safe='')}"


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
    static_url=static_url,
    login_url=login_url,
    TAB_LABELS=TAB_LABELS,
    TAB_ICONS=TAB_ICONS,
)
templates.env.filters.update(milhar=format_thousands, nota=format_rating, servicos=watch_services,
                             porcento=format_percent, ep=format_episode,
                             data=format_date, tempo_tv=format_watch_time,
                             tempo_partes=watch_time_parts, tempo_unidades=watch_time_units)
