"""HTTP health and readiness behavior."""

import sqlite3

from fastapi.testclient import TestClient

from app.db import SCHEMA_VERSION
from app.main import create_app


def test_root_health_and_readiness(tmp_path):
    database_path = tmp_path / "health.db"

    with TestClient(create_app(database_path)) as client:
        root_response = client.get("/")
        health_response = client.get("/healthz")
        readiness_response = client.get("/readyz")

    assert root_response.status_code == 200
    assert "Huddle App Lite" in root_response.text
    assert health_response.json() == {"status": "ok"}
    assert readiness_response.json() == {"status": "ready"}
    assert database_path.exists()


def test_readiness_hides_database_failure_details(tmp_path):
    database_path = tmp_path / "not-ready.db"

    with TestClient(create_app(database_path)) as client:
        with sqlite3.connect(database_path) as connection:
            connection.execute("PRAGMA user_version = 0")

        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}
    assert str(database_path) not in response.text


def test_liveness_remains_available_for_unsupported_schema(tmp_path):
    database_path = tmp_path / "future-schema.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with TestClient(create_app(database_path)) as client:
        health_response = client.get("/healthz")
        readiness_response = client.get("/readyz")

    assert health_response.json() == {"status": "ok"}
    assert readiness_response.status_code == 503
    assert readiness_response.json() == {"status": "not ready"}
