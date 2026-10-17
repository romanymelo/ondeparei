"""Para onde leva o "← Voltar" da página da série: a última lista vista (catálogo, busca ou Minhas séries).

As páginas de lista gravam o próprio endereço num cookie; a página da série lê e valida esse cookie.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import Request, Response

LIST_COOKIE = "ultima_lista"
LIST_PATHS = ("/", "/buscar", "/minhas-series")
HOME = "/"


def list_url(path: str, query_items) -> str:
    """Endereço da lista sem `pagina`: voltar sempre reabre a lista do começo, com os mesmos filtros."""
    query = urlencode([(k, v) for k, v in query_items if k != "pagina"])
    return f"{path}?{query}" if query else path


def remember_list(request: Request, response: Response) -> Response:
    url = list_url(request.url.path, request.query_params.multi_items())
    response.set_cookie(LIST_COOKIE, url, httponly=True, samesite="lax")
    return response


def _safe_list(url: str | None) -> str | None:
    """Só aceita um endereço relativo de uma das listas; qualquer outra coisa é descartada."""
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or parts.path not in LIST_PATHS:
        return None
    return list_url(parts.path, parse_qsl(parts.query, keep_blank_values=True))


def back_target(request: Request) -> tuple[str, bool]:
    """(endereço do Voltar, se a página anterior é essa mesma lista — aí o voltar do navegador mantém a rolagem)."""
    target = _safe_list(request.cookies.get(LIST_COOKIE)) or HOME
    referer = urlsplit(request.headers.get("referer", ""))
    came_from_list = (referer.netloc == request.url.netloc
                      and _safe_list(f"{referer.path}?{referer.query}") == target)
    return target, came_from_list
