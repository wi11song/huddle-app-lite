"""Meeting suggestions API integration tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def create_event(
    client: TestClient,
    *,
    dates: list[str] | None = None,
    day_start_minute: int = 780,
    day_end_minute: int = 960,
    slot_minutes: int = 30,
) -> str:
    response = client.post(
        "/api/events",
        json={
            "name": "Suggestion Test",
            "dates": dates or ["2026-11-23", "2026-11-24"],
            "day_start_minute": day_start_minute,
            "day_end_minute": day_end_minute,
            "slot_minutes": slot_minutes,
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 201
    return response.json()["slug"]


def join_and_save(
    client: TestClient,
    slug: str,
    name: str,
    availability: str,
) -> None:
    join_response = client.post(
        f"/api/events/{slug}/participants",
        json={"name": name},
    )
    assert join_response.status_code == 200

    save_response = client.put(
        (
            f"/api/events/{slug}/participants/"
            f"{join_response.json()['participant_id']}/availability"
        ),
        json={"availability": availability},
        headers={"X-Edit-Token": join_response.json()["edit_token"]},
    )
    assert save_response.status_code == 204


def test_suggestions_find_three_participant_common_window(tmp_path):
    with TestClient(create_app(tmp_path / "acceptance.db")) as client:
        slug = create_event(client)
        join_and_save(client, slug, "Alice", "110000001100")
        join_and_save(client, slug, "Bob", "001100001100")
        join_and_save(client, slug, "Cara", "000011001100")

        response = client.get(
            f"/api/events/{slug}/suggestions",
            params={"duration_minutes": 60},
        )

    assert response.status_code == 200
    assert response.json() == {
        "earliest_common_slot": 8,
        "best_windows": [
            {
                "start_slot": 8,
                "attendee_count": 3,
                "attendee_names": ["Alice", "Bob", "Cara"],
            },
            {
                "start_slot": 0,
                "attendee_count": 1,
                "attendee_names": ["Alice"],
            },
            {
                "start_slot": 2,
                "attendee_count": 1,
                "attendee_names": ["Bob"],
            },
        ],
    }


def test_suggestions_return_partial_windows_without_common_time(tmp_path):
    with TestClient(create_app(tmp_path / "partial.db")) as client:
        slug = create_event(
            client,
            dates=["2026-11-23"],
            day_start_minute=540,
            day_end_minute=660,
        )
        join_and_save(client, slug, "Alice", "1100")
        join_and_save(client, slug, "Bob", "0011")

        response = client.get(
            f"/api/events/{slug}/suggestions",
            params={"duration_minutes": 60},
        )

    assert response.status_code == 200
    assert response.json() == {
        "earliest_common_slot": None,
        "best_windows": [
            {
                "start_slot": 0,
                "attendee_count": 1,
                "attendee_names": ["Alice"],
            },
            {
                "start_slot": 2,
                "attendee_count": 1,
                "attendee_names": ["Bob"],
            },
            {
                "start_slot": 1,
                "attendee_count": 0,
                "attendee_names": [],
            },
        ],
    }


def test_duration_rounds_up_to_whole_slots(tmp_path):
    with TestClient(create_app(tmp_path / "rounding.db")) as client:
        slug = create_event(
            client,
            dates=["2026-11-23"],
            day_start_minute=540,
            day_end_minute=660,
        )
        join_and_save(client, slug, "Alice", "1100")

        response = client.get(
            f"/api/events/{slug}/suggestions",
            params={"duration_minutes": 31},
        )

    assert response.status_code == 200
    assert response.json()["earliest_common_slot"] == 0
    assert response.json()["best_windows"][0]["start_slot"] == 0


def test_suggestions_never_cross_day_boundary(tmp_path):
    with TestClient(create_app(tmp_path / "boundary.db")) as client:
        slug = create_event(
            client,
            day_start_minute=540,
            day_end_minute=600,
        )
        join_and_save(client, slug, "Alice", "0110")

        response = client.get(
            f"/api/events/{slug}/suggestions",
            params={"duration_minutes": 60},
        )

    assert response.status_code == 200
    assert response.json() == {
        "earliest_common_slot": None,
        "best_windows": [
            {
                "start_slot": 0,
                "attendee_count": 0,
                "attendee_names": [],
            },
            {
                "start_slot": 2,
                "attendee_count": 0,
                "attendee_names": [],
            },
        ],
    }


def test_suggestions_without_participants_are_empty(tmp_path):
    with TestClient(create_app(tmp_path / "empty.db")) as client:
        slug = create_event(client)
        response = client.get(f"/api/events/{slug}/suggestions")

    assert response.status_code == 200
    assert response.json() == {
        "earliest_common_slot": None,
        "best_windows": [],
    }


def test_suggestions_for_unknown_event_return_not_found(tmp_path):
    with TestClient(create_app(tmp_path / "missing.db")) as client:
        response = client.get("/api/events/unknown/suggestions")

    assert response.status_code == 404
    assert response.json() == {"detail": "event not found"}


@pytest.mark.parametrize("duration_minutes", [0, -1, 1441])
def test_suggestions_reject_invalid_duration_query(tmp_path, duration_minutes):
    with TestClient(create_app(tmp_path / "invalid.db")) as client:
        slug = create_event(client)
        response = client.get(
            f"/api/events/{slug}/suggestions",
            params={"duration_minutes": duration_minutes},
        )

    assert response.status_code == 422


def test_suggestions_reject_duration_longer_than_daily_window(tmp_path):
    with TestClient(create_app(tmp_path / "too-long.db")) as client:
        slug = create_event(
            client,
            day_start_minute=540,
            day_end_minute=600,
        )
        response = client.get(
            f"/api/events/{slug}/suggestions",
            params={"duration_minutes": 61},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "duration exceeds the event's daily window"
    }
