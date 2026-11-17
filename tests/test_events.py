"""Event creation and retrieval API tests."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def event_payload(**overrides):
    payload = {
        "name": "Architecture Review",
        "schedule_kind": "dates",
        "dates": ["2026-11-18", "2026-11-17"],
        "day_start_minute": 540,
        "day_end_minute": 600,
        "slot_minutes": 30,
        "timezone": "America/New_York",
    }
    payload.update(overrides)
    return payload


def test_create_and_get_event(tmp_path):
    database_path = tmp_path / "events.db"

    with TestClient(create_app(database_path)) as client:
        create_response = client.post("/api/events", json=event_payload())
        slug = create_response.json()["slug"]
        get_response = client.get(f"/api/events/{slug}")

    assert create_response.status_code == 201
    assert len(slug) == 12
    assert get_response.status_code == 200
    assert get_response.json() == {
        "event": {
            "slug": slug,
            "name": "Architecture Review",
            "schedule_kind": "dates",
            "dates": ["2026-11-17", "2026-11-18"],
            "day_start_minute": 540,
            "day_end_minute": 600,
            "slot_minutes": 30,
            "timezone": "America/New_York",
            "revision": 0,
            "created_at": get_response.json()["event"]["created_at"],
            "updated_at": get_response.json()["event"]["updated_at"],
            "slot_count": 4,
        },
        "participants": [],
        "free_counts": [0, 0, 0, 0],
        "version": 0,
    }
    assert get_response.json()["event"]["created_at"].endswith("Z")
    assert (
        get_response.json()["event"]["created_at"]
        == get_response.json()["event"]["updated_at"]
    )


def test_create_event_persists_canonical_values(tmp_path):
    database_path = tmp_path / "persisted.db"

    with TestClient(create_app(database_path)) as client:
        response = client.post(
            "/api/events",
            json=event_payload(name="  Planning Session  "),
        )

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT name, schedule_kind, dates, revision FROM events"
        ).fetchone()

    assert response.status_code == 201
    assert row == (
        "Planning Session",
        "dates",
        json.dumps(["2026-11-17", "2026-11-18"], separators=(",", ":")),
        0,
    )


def test_create_weekday_event_normalizes_display_order(tmp_path):
    database_path = tmp_path / "weekdays.db"

    with TestClient(create_app(database_path)) as client:
        create_response = client.post(
            "/api/events",
            json=event_payload(
                schedule_kind="weekdays",
                dates=["fri", "MON", "wed"],
            ),
        )
        event_response = client.get(
            f"/api/events/{create_response.json()['slug']}"
        )

    assert create_response.status_code == 201
    assert event_response.json()["event"]["dates"] == ["MON", "WED", "FRI"]
    assert event_response.json()["event"]["slot_count"] == 6


def test_event_slugs_are_unique(tmp_path):
    database_path = tmp_path / "unique.db"

    with TestClient(create_app(database_path)) as client:
        first_slug = client.post("/api/events", json=event_payload()).json()["slug"]
        second_slug = client.post("/api/events", json=event_payload()).json()["slug"]

    assert first_slug != second_slug


def test_get_unknown_event_returns_not_found(tmp_path):
    with TestClient(create_app(tmp_path / "missing.db")) as client:
        response = client.get("/api/events/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "event not found"}


def test_events_are_isolated_by_database(tmp_path):
    first_database = tmp_path / "first.db"
    second_database = tmp_path / "second.db"

    with TestClient(create_app(first_database)) as first_client:
        slug = first_client.post("/api/events", json=event_payload()).json()["slug"]

    with TestClient(create_app(second_database)) as second_client:
        response = second_client.get(f"/api/events/{slug}")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "   "}, "name"),
        ({"dates": []}, "dates"),
        ({"dates": ["2026-11-17", "2026-11-17"]}, "duplicates"),
        ({"dates": ["November 17"]}, "ISO dates"),
        ({"timezone": "Mars/Olympus"}, "IANA"),
        ({"day_start_minute": 600, "day_end_minute": 600}, "precede"),
        ({"day_end_minute": 605}, "divide evenly"),
        ({"slot_minutes": 20}, "Input should be 15, 30 or 60"),
        (
            {"schedule_kind": "weekdays", "dates": ["MON", "SOMEDAY"]},
            "MON through SUN",
        ),
    ],
)
def test_create_event_rejects_invalid_input(tmp_path, overrides, message):
    with TestClient(create_app(tmp_path / "invalid.db")) as client:
        response = client.post(
            "/api/events",
            json=event_payload(**overrides),
        )

    assert response.status_code == 422
    assert message in response.text
