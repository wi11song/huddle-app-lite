"""SQLite initialization and isolation tests."""

import sqlite3

import pytest

from app.db import (
    SCHEMA_VERSION,
    DatabaseNotReadyError,
    check_readiness,
    connect,
    initialize_database,
    resolve_database_path,
)


def test_initialize_database_creates_reviewed_schema(tmp_path):
    database_path = initialize_database(tmp_path / "foundation.db")

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert {"events", "participants", "participant_sessions"} <= tables
    assert schema_version == SCHEMA_VERSION
    assert journal_mode == "wal"
    check_readiness(database_path)


def test_connection_enables_foreign_keys(tmp_path):
    database_path = initialize_database(tmp_path / "foreign-keys.db")

    with connect(database_path) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert foreign_keys_enabled == 1


def test_explicit_database_path_overrides_runner_environment(tmp_path, monkeypatch):
    inherited_path = tmp_path / "inherited.db"
    isolated_path = tmp_path / "isolated.db"
    monkeypatch.setenv("HUDDLE_DB_PATH", str(inherited_path))

    resolved_path = resolve_database_path(isolated_path)
    initialize_database(resolved_path)

    assert resolved_path == isolated_path
    assert isolated_path.exists()
    assert not inherited_path.exists()


def test_environment_database_path_is_used_when_no_explicit_path(
    tmp_path, monkeypatch
):
    configured_path = tmp_path / "configured.db"
    monkeypatch.setenv("HUDDLE_DB_PATH", str(configured_path))

    assert resolve_database_path() == configured_path


def test_unknown_schema_version_is_rejected(tmp_path):
    database_path = tmp_path / "future.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(DatabaseNotReadyError, match="unsupported database schema"):
        initialize_database(database_path)


def test_readiness_does_not_create_a_missing_database(tmp_path):
    database_path = tmp_path / "missing.db"

    with pytest.raises(sqlite3.OperationalError):
        check_readiness(database_path)

    assert not database_path.exists()
