"""Authenticated availability save and event revision API tests."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import hash_edit_token


def create_event(client: TestClient) -> str:
    response = client.post(
        "/api/events",
        json={
            "name": "Availability Test",
            "dates": ["2026-11-23", "2026-11-24"],
            "day_start_minute": 540,
            "day_end_minute": 600,
            "slot_minutes": 30,
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 201
    return response.json()["slug"]


def join_participant(
    client: TestClient,
    slug: str,
    name: str = "Alice",
) -> tuple[int, str]:
    response = client.post(
        f"/api/events/{slug}/participants",
        json={"name": name},
    )
    assert response.status_code == 200
    return response.json()["participant_id"], response.json()["edit_token"]


def availability_url(slug: str, participant_id: int) -> str:
    return (
        f"/api/events/{slug}/participants/"
        f"{participant_id}/availability"
    )


def test_save_availability_updates_heatmap_revision_and_session(tmp_path):
    database_path = tmp_path / "availability.db"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        participant_id, edit_token = join_participant(client, slug)
        initial_version = client.get(f"/api/events/{slug}/version")
        save_response = client.put(
            availability_url(slug, participant_id),
            json={"availability": "1010"},
            headers={"X-Edit-Token": edit_token},
        )
        updated_version = client.get(f"/api/events/{slug}/version")
        event_response = client.get(f"/api/events/{slug}")

    assert initial_version.json() == {"version": 1}
    assert save_response.status_code == 204
    assert save_response.content == b""
    assert updated_version.json() == {"version": 2}
    assert event_response.json()["participants"][0]["availability"] == "1010"
    assert event_response.json()["free_counts"] == [1, 0, 1, 0]
    assert event_response.json()["event"]["revision"] == 2

    with sqlite3.connect(database_path) as connection:
        last_used_at = connection.execute(
            """
            SELECT last_used_at
            FROM participant_sessions
            WHERE token_hash = ?
            """,
            (hash_edit_token(edit_token),),
        ).fetchone()[0]

    assert last_used_at is not None
    assert last_used_at.endswith("Z")


def test_each_successful_save_increments_revision(tmp_path):
    database_path = tmp_path / "revision.db"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        participant_id, edit_token = join_participant(client, slug)
        for availability in ("1000", "1100", "1110"):
            response = client.put(
                availability_url(slug, participant_id),
                json={"availability": availability},
                headers={"X-Edit-Token": edit_token},
            )
            assert response.status_code == 204

        version_response = client.get(f"/api/events/{slug}/version")

    assert version_response.json() == {"version": 4}


def test_wrong_token_does_not_change_availability_or_revision(tmp_path):
    database_path = tmp_path / "unauthorized.db"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        participant_id, _edit_token = join_participant(client, slug)
        response = client.put(
            availability_url(slug, participant_id),
            json={"availability": "1111"},
            headers={"X-Edit-Token": "not-the-token"},
        )
        event_response = client.get(f"/api/events/{slug}")

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid edit token"}
    assert event_response.json()["version"] == 1
    assert event_response.json()["participants"][0]["availability"] == "0000"


def test_participant_cannot_use_another_participants_token(tmp_path):
    database_path = tmp_path / "ownership.db"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        alice_id, _alice_token = join_participant(client, slug, "Alice")
        _bob_id, bob_token = join_participant(client, slug, "Bob")
        response = client.put(
            availability_url(slug, alice_id),
            json={"availability": "1111"},
            headers={"X-Edit-Token": bob_token},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid edit token"}


def test_participant_must_belong_to_route_event(tmp_path):
    database_path = tmp_path / "event-ownership.db"

    with TestClient(create_app(database_path)) as client:
        first_slug = create_event(client)
        second_slug = create_event(client)
        participant_id, edit_token = join_participant(client, first_slug)
        response = client.put(
            availability_url(second_slug, participant_id),
            json={"availability": "1111"},
            headers={"X-Edit-Token": edit_token},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "participant not found"}


@pytest.mark.parametrize(
    "availability",
    ["101", "10101", "10x0"],
)
def test_invalid_availability_does_not_change_revision(
    tmp_path,
    availability,
):
    database_path = tmp_path / f"invalid-{len(availability)}.db"

    with TestClient(create_app(database_path)) as client:
        slug = create_event(client)
        participant_id, edit_token = join_participant(client, slug)
        response = client.put(
            availability_url(slug, participant_id),
            json={"availability": availability},
            headers={"X-Edit-Token": edit_token},
        )
        version_response = client.get(f"/api/events/{slug}/version")

    assert response.status_code == 422
    assert version_response.json() == {"version": 1}


def test_save_requires_edit_token_header(tmp_path):
    with TestClient(create_app(tmp_path / "header.db")) as client:
        slug = create_event(client)
        participant_id, _edit_token = join_participant(client, slug)
        response = client.put(
            availability_url(slug, participant_id),
            json={"availability": "1111"},
        )

    assert response.status_code == 422


def test_unknown_participant_and_event_return_not_found(tmp_path):
    with TestClient(create_app(tmp_path / "missing.db")) as client:
        slug = create_event(client)
        unknown_participant = client.put(
            availability_url(slug, 999),
            json={"availability": "1111"},
            headers={"X-Edit-Token": "token"},
        )
        unknown_event = client.put(
            availability_url("unknown", 999),
            json={"availability": "1111"},
            headers={"X-Edit-Token": "token"},
        )
        unknown_version = client.get("/api/events/unknown/version")

    assert unknown_participant.status_code == 404
    assert unknown_participant.json() == {"detail": "participant not found"}
    assert unknown_event.status_code == 404
    assert unknown_event.json() == {"detail": "event not found"}
    assert unknown_version.status_code == 404
    assert unknown_version.json() == {"detail": "event not found"}
