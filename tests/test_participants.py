"""Participant join, sign-in, and session API tests."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import hash_edit_token, verify_password


def create_event(client: TestClient) -> str:
    response = client.post(
        "/api/events",
        json={
            "name": "Team Huddle",
            "dates": ["2026-11-23", "2026-11-24"],
            "day_start_minute": 540,
            "day_end_minute": 600,
            "slot_minutes": 30,
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 201
    return response.json()["slug"]


def test_new_participant_receives_session_and_appears_in_event(tmp_path):
    database_path = tmp_path / "participant.db"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        join_response = client.post(
            f"/api/events/{slug}/participants",
            json={"name": "  Alice  "},
        )
        event_response = client.get(f"/api/events/{slug}")

    assert join_response.status_code == 200
    participant_id = join_response.json()["participant_id"]
    edit_token = join_response.json()["edit_token"]
    assert participant_id > 0
    assert len(edit_token) >= 43
    assert event_response.json()["participants"] == [
        {
            "id": participant_id,
            "name": "Alice",
            "availability": "0000",
        }
    ]
    assert event_response.json()["free_counts"] == [0, 0, 0, 0]
    assert event_response.json()["version"] == 1
    assert event_response.json()["event"]["revision"] == 1

    with sqlite3.connect(database_path) as connection:
        participant_row = connection.execute(
            "SELECT name_key, password_hash FROM participants"
        ).fetchone()
        session_hash = connection.execute(
            "SELECT token_hash FROM participant_sessions"
        ).fetchone()[0]

    assert participant_row == ("alice", None)
    assert session_hash == hash_edit_token(edit_token)
    assert session_hash != edit_token


def test_passwordless_participant_can_return_with_casefolded_name(tmp_path):
    database_path = tmp_path / "returning.db"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        first_response = client.post(
            f"/api/events/{slug}/participants",
            json={"name": "Straße"},
        )
        second_response = client.post(
            f"/api/events/{slug}/participants",
            json={"name": "STRASSE"},
        )
        event_response = client.get(f"/api/events/{slug}")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert (
        first_response.json()["participant_id"]
        == second_response.json()["participant_id"]
    )
    assert first_response.json()["edit_token"] != second_response.json()["edit_token"]
    assert event_response.json()["version"] == 1
    assert [participant["name"] for participant in event_response.json()["participants"]] == [
        "Straße"
    ]

    with sqlite3.connect(database_path) as connection:
        participant_count = connection.execute(
            "SELECT count(*) FROM participants"
        ).fetchone()[0]
        session_count = connection.execute(
            "SELECT count(*) FROM participant_sessions"
        ).fetchone()[0]

    assert participant_count == 1
    assert session_count == 2


def test_password_protected_participant_requires_correct_password(tmp_path):
    database_path = tmp_path / "password.db"
    password = "correct horse battery staple"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        first_response = client.post(
            f"/api/events/{slug}/participants",
            json={"name": "Bob", "password": password},
        )
        correct_response = client.post(
            f"/api/events/{slug}/participants",
            json={"name": "bob", "password": password},
        )
        wrong_response = client.post(
            f"/api/events/{slug}/participants",
            json={"name": "BOB", "password": "wrong"},
        )
        missing_response = client.post(
            f"/api/events/{slug}/participants",
            json={"name": "Bob"},
        )

    assert first_response.status_code == 200
    assert correct_response.status_code == 200
    assert (
        first_response.json()["participant_id"]
        == correct_response.json()["participant_id"]
    )
    assert wrong_response.status_code == 401
    assert wrong_response.json() == {"detail": "invalid participant password"}
    assert missing_response.status_code == 401

    with sqlite3.connect(database_path) as connection:
        password_hash = connection.execute(
            "SELECT password_hash FROM participants"
        ).fetchone()[0]
        session_count = connection.execute(
            "SELECT count(*) FROM participant_sessions"
        ).fetchone()[0]

    assert password_hash != password
    assert verify_password(password, password_hash)
    assert session_count == 2


def test_same_name_is_isolated_between_events(tmp_path):
    database_path = tmp_path / "events.db"

    with TestClient(create_app(database_path)) as client:
        first_slug = create_event(client)
        second_slug = create_event(client)
        first_response = client.post(
            f"/api/events/{first_slug}/participants",
            json={"name": "Alice"},
        )
        second_response = client.post(
            f"/api/events/{second_slug}/participants",
            json={"name": "Alice"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert (
        first_response.json()["participant_id"]
        != second_response.json()["participant_id"]
    )


def test_join_unknown_event_returns_not_found(tmp_path):
    with TestClient(create_app(tmp_path / "unknown.db")) as client:
        response = client.post(
            "/api/events/unknown/participants",
            json={"name": "Alice"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "event not found"}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"name": "a" * 51},
        {"name": "Alice", "password": ""},
        {"name": "Alice", "password": "a" * 129},
    ],
)
def test_join_rejects_invalid_participant_input(tmp_path, payload):
    with TestClient(create_app(tmp_path / "invalid.db")) as client:
        slug = create_event(client)
        response = client.post(
            f"/api/events/{slug}/participants",
            json=payload,
        )

    assert response.status_code == 422
