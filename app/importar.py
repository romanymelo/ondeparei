"""Importação única: leva as marcações do data/catalogo.db (fase 2a) para uma conta do Supabase.

Uso: uv run python -m app.importar seu@email.com
Precisa de SUPABASE_SECRET_KEY no .env. Pode rodar de novo: não duplica nada (upsert).
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.auth.client import admin_headers
from app.config import ConfigError, load_settings
from app.templating import format_watch_time
from app.tracking.db import connect

BATCH = 500
PAGE = 200
READ_PAGE = 1000  # limite padrão de linhas por resposta do PostgREST
NO_SECRET = "SUPABASE_SECRET_KEY não definido no .env (necessário só para a importação)."


@dataclass(frozen=True)
class Summary:
    series: int
    episodes: int
    minutes_before: int
    minutes_after: int


async def _find_user(http: httpx.AsyncClient, url: str, headers: dict, email: str) -> str:
    wanted = email.strip().lower()
    page = 1
    while True:
        response = await http.get(f"{url}/auth/v1/admin/users", params={"page": str(page), "per_page": str(PAGE)},
                                  headers=headers)
        response.raise_for_status()
        users = response.json().get("users") or []
        if not users:
            raise LookupError("Conta não encontrada: crie a conta no app primeiro.")
        for user in users:
            if (user.get("email") or "").lower() == wanted:
                return user["id"]
        page += 1


async def _upsert(http: httpx.AsyncClient, url: str, headers: dict, table: str, conflict: str, rows: list[dict]):
    # ignore-duplicates: rodar de novo não traz o estado antigo por cima do que mudou no app
    upsert = headers | {"Prefer": "resolution=ignore-duplicates,return=minimal"}
    for start in range(0, len(rows), BATCH):
        response = await http.post(f"{url}/rest/v1/{table}", params={"on_conflict": conflict},
                                   json=rows[start:start + BATCH], headers=upsert)
        response.raise_for_status()


async def _minutes_in_account(http: httpx.AsyncClient, url: str, headers: dict, user_id: str) -> int:
    total, offset = 0, 0
    while True:
        response = await http.get(f"{url}/rest/v1/watched_episodes", headers=headers, params={
            "select": "runtime", "user_id": f"eq.{user_id}", "order": "tmdb_id,season,episode",
            "limit": str(READ_PAGE), "offset": str(offset)})
        response.raise_for_status()
        rows = response.json()
        total += sum(row.get("runtime") or 0 for row in rows)
        if len(rows) < READ_PAGE:
            return total
        offset += READ_PAGE


async def import_local(db_path: str | Path, email: str, http: httpx.AsyncClient, url: str,
                       secret_key: str) -> Summary:
    url = url.rstrip("/")
    headers = admin_headers(secret_key)
    user_id = await _find_user(http, url, headers, email)

    conn = connect(db_path)
    try:
        series = [{"user_id": user_id, "tmdb_id": tmdb_id, "status": status, "favorite": bool(favorite),
                   "name": name, "poster_path": poster_path, "updated_at": updated_at}
                  for tmdb_id, status, favorite, name, poster_path, updated_at in conn.execute(
                      "SELECT tmdb_id, status, favorite, name, poster_path, updated_at FROM series_tracking")]
        episodes = [{"user_id": user_id, "tmdb_id": tmdb_id, "season": season, "episode": episode,
                     "watched_at": watched_at, "runtime": runtime}
                    for tmdb_id, season, episode, watched_at, runtime in conn.execute(
                        "SELECT tmdb_id, season, episode, watched_at, runtime FROM watched_episodes")]
    finally:
        conn.close()

    await _upsert(http, url, headers, "series_tracking", "user_id,tmdb_id", series)
    await _upsert(http, url, headers, "watched_episodes", "user_id,tmdb_id,season,episode", episodes)
    minutes_before = sum(row["runtime"] or 0 for row in episodes)
    minutes_after = await _minutes_in_account(http, url, headers, user_id)
    return Summary(len(series), len(episodes), minutes_before, minutes_after)


def main(argv: list[str] | None = None, env_file: str | None = ".env") -> int:
    args = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # terminal do Windows (cp1252) e a seta do resumo
    if len(args) != 1:
        print("Uso: uv run python -m app.importar seu@email.com", file=sys.stderr)
        return 2
    try:
        settings = load_settings(env_file)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    if settings.supabase_secret_key is None or not settings.supabase_secret_key.get_secret_value().strip():
        print(NO_SECRET, file=sys.stderr)
        return 2

    async def run() -> Summary:
        async with httpx.AsyncClient(timeout=30) as http:
            return await import_local(settings.database_path, args[0], http, settings.supabase_url,
                                      settings.supabase_secret_key.get_secret_value())

    try:
        summary = asyncio.run(run())
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Importado: {summary.series} séries, {summary.episodes} episódios. "
          f"Tempo de séries: {format_watch_time(summary.minutes_before)} → {format_watch_time(summary.minutes_after)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
