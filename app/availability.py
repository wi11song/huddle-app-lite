"""Authenticated participant availability persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .db import connect
from .participants import EventNotFoundError
from .security import verify_edit_token


class ParticipantNotFoundError(LookupError):
    """Raised when a participant does not belong to the requested event."""


class InvalidEditTokenError(PermissionError):
    """Raised when an edit token does not authorize a participant."""


class InvalidAvailabilityError(ValueError):
    """Raised when availability does not match the event's slot grid."""


def save_availability(
    database_path: Path | str,
    event_slug: str,
    participant_id: int,
    availability: str,
    edit_token: str,
) -> int:
    """Save one participant's availability and return the new event revision."""
    timestamp = _utc_timestamp()

    with connect(database_path, existing=True) as connection:
        event_row = connection.execute(
            """
            SELECT
                id,
                dates,
                day_start_minute,
                day_end_minute,
                slot_minutes,
                revision
            FROM events
            WHERE slug = ?
            """,
            (event_slug,),
        ).fetchone()
        if event_row is None:
            raise EventNotFoundError(event_slug)

        participant_row = connection.execute(
            """
            SELECT id
            FROM participants
            WHERE id = ? AND event_id = ?
            """,
            (participant_id, event_row["id"]),
        ).fetchone()
        if participant_row is None:
            raise ParticipantNotFoundError(participant_id)

        session_rows = connection.execute(
            """
            SELECT token_hash
            FROM participant_sessions
            WHERE participant_id = ?
            """,
            (participant_id,),
        ).fetchall()
        matching_token_hash = next(
            (
                row["token_hash"]
                for row in session_rows
                if verify_edit_token(edit_token, row["token_hash"])
            ),
            None,
        )
        if matching_token_hash is None:
            raise InvalidEditTokenError()

        _validate_availability(availability, event_row)

        connection.execute("BEGIN IMMEDIATE")
        participant_update = connection.execute(
            """
            UPDATE participants
            SET availability = ?,
                updated_at = ?
            WHERE id = ? AND event_id = ?
            """,
            (
                availability,
                timestamp,
                participant_id,
                event_row["id"],
            ),
        )
        if participant_update.rowcount != 1:
            raise ParticipantNotFoundError(participant_id)

        connection.execute(
            """
            UPDATE participant_sessions
            SET last_used_at = ?
            WHERE token_hash = ?
            """,
            (timestamp, matching_token_hash),
        )
        connection.execute(
            """
            UPDATE events
            SET revision = revision + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (timestamp, event_row["id"]),
        )

    return int(event_row["revision"]) + 1


def _validate_availability(availability: str, event_row) -> None:
    dates = json.loads(event_row["dates"])
    slots_per_day = (
        event_row["day_end_minute"] - event_row["day_start_minute"]
    ) // event_row["slot_minutes"]
    expected_length = len(dates) * slots_per_day

    if len(availability) != expected_length:
        raise InvalidAvailabilityError(
            f"availability must contain exactly {expected_length} slots"
        )
    if set(availability) - {"0", "1"}:
        raise InvalidAvailabilityError(
            "availability must contain only 0 and 1"
        )


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
