"""SQLite connection, schema initialization, and readiness checks."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DATABASE_ENVIRONMENT_VARIABLE = "HUDDLE_DB_PATH"
DEFAULT_DATABASE_PATH = Path("huddle.db")
SCHEMA_VERSION = 1

SCHEMA_SQL = """
BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS events (
    id               INTEGER PRIMARY KEY,
    slug             TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    schedule_kind    TEXT    NOT NULL
                     CHECK (schedule_kind IN ('dates', 'weekdays')),
    dates            TEXT    NOT NULL,
    day_start_minute INTEGER NOT NULL,
    day_end_minute   INTEGER NOT NULL,
    slot_minutes     INTEGER NOT NULL DEFAULT 15
                     CHECK (slot_minutes IN (15, 30, 60)),
    timezone         TEXT    NOT NULL,
    revision         INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    CHECK (
        day_start_minute >= 0
        AND day_start_minute < day_end_minute
        AND day_end_minute <= 1440
        AND (day_end_minute - day_start_minute) % slot_minutes = 0
    )
);

CREATE TABLE IF NOT EXISTS participants (
    id            INTEGER PRIMARY KEY,
    event_id      INTEGER NOT NULL
                  REFERENCES events(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL CHECK (length(name) BETWEEN 1 AND 50),
    name_key      TEXT    NOT NULL CHECK (length(name_key) >= 1),
    password_hash TEXT,
    availability  TEXT    NOT NULL
                  CHECK (
                      availability <> ''
                      AND availability NOT GLOB '*[^01]*'
                  ),
    updated_at    TEXT    NOT NULL,
    UNIQUE (event_id, name_key)
);

CREATE TABLE IF NOT EXISTS participant_sessions (
    token_hash     TEXT PRIMARY KEY,
    participant_id INTEGER NOT NULL
                   REFERENCES participants(id) ON DELETE CASCADE,
    created_at     TEXT NOT NULL,
    last_used_at   TEXT
);
"""


class DatabaseNotReadyError(RuntimeError):
    """Raised when the configured database does not have the expected schema."""


def resolve_database_path(database_path: Path | str | None = None) -> Path:
    """Resolve an explicit path, environment override, or local default."""
    if database_path is not None:
        return Path(database_path).expanduser()
    configured_path = os.environ.get(DATABASE_ENVIRONMENT_VARIABLE)
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_DATABASE_PATH


def connect(database_path: Path | str, *, existing: bool = False) -> sqlite3.Connection:
    """Open a configured short-lived SQLite connection."""
    resolved_path = Path(database_path)
    if existing:
        connection = sqlite3.connect(
            f"file:{resolved_path}?mode=rw",
            uri=True,
            timeout=5,
        )
    else:
        connection = sqlite3.connect(resolved_path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(database_path: Path | str | None = None) -> Path:
    """Create or validate the schema and return the resolved database path."""
    resolved_path = resolve_database_path(database_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(resolved_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version not in (0, SCHEMA_VERSION):
            raise DatabaseNotReadyError(
                f"unsupported database schema version {current_version}"
            )
        if current_version == 0:
            connection.executescript(
                f"{SCHEMA_SQL}\n"
                f"PRAGMA user_version = {SCHEMA_VERSION};\n"
                "COMMIT;"
            )

    return resolved_path


def check_readiness(database_path: Path | str) -> None:
    """Verify connectivity and the exact schema version without creating a DB."""
    with connect(database_path, existing=True) as connection:
        connection.execute("SELECT 1").fetchone()
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version != SCHEMA_VERSION:
            raise DatabaseNotReadyError(
                f"expected schema version {SCHEMA_VERSION}, got {current_version}"
            )
