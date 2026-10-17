"""Banco SQLite das marcações: abre a conexão e aplica as migrações pendentes (PRAGMA user_version)."""

import sqlite3
from pathlib import Path

MIGRATION_1 = """
CREATE TABLE series_tracking (
    user_id     INTEGER NOT NULL DEFAULT 1,
    tmdb_id     INTEGER NOT NULL,
    status      TEXT CHECK (status IN ('want', 'watching', 'watched')),  -- NULL = sem status
    favorite    INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
    name        TEXT NOT NULL,
    poster_path TEXT,
    updated_at  TEXT NOT NULL,  -- ISO 8601 UTC
    PRIMARY KEY (user_id, tmdb_id)
);

CREATE TABLE watched_episodes (
    user_id    INTEGER NOT NULL DEFAULT 1,
    tmdb_id    INTEGER NOT NULL,
    season     INTEGER NOT NULL,
    episode    INTEGER NOT NULL,
    watched_at TEXT NOT NULL,
    PRIMARY KEY (user_id, tmdb_id, season, episode)
);
"""

# duração do episódio em minutos, para o contador de tempo assistido (NULL = ainda não conhecida)
MIGRATION_2 = """
ALTER TABLE watched_episodes ADD COLUMN runtime INTEGER;
"""

MIGRATIONS: tuple[str, ...] = (MIGRATION_1, MIGRATION_2)


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Aplica, cada uma numa transação, as migrações de índice ≥ user_version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
