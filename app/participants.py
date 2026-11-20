"""Participant join, sign-in, and edit-session persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import connect
from .models import ParticipantJoin
from .security import (
    create_edit_token,
    hash_edit_token,
    hash_password,
    verify_password,
)


class EventNotFoundError(LookupError):
    """Raised when a participant references an unknown event."""


class InvalidParticipantPasswordError(PermissionError):
    """Raised when a protected participant cannot be authenticated."""


@dataclass(frozen=True)
class ParticipantJoinResult:
    """Participant identity and newly issued edit token."""

    participant_id: int
    edit_token: str


def join_participant(
    database_path: Path | str,
    event_slug: str,
    request: ParticipantJoin,
) -> ParticipantJoinResult:
    """Create or authenticate a participant and issue an independent session."""
    timestamp = _utc_timestamp()
    name_key = request.name.casefold()
    edit_token = create_edit_token()

    with connect(database_path, existing=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        event_row = connection.execute(
            """
            SELECT id, dates, day_start_minute, day_end_minute, slot_minutes
            FROM events
            WHERE slug = ?
            """,
            (event_slug,),
        ).fetchone()
        if event_row is None:
            raise EventNotFoundError(event_slug)

        participant_row = connection.execute(
            """
            SELECT id, password_hash
            FROM participants
            WHERE event_id = ? AND name_key = ?
            """,
            (event_row["id"], name_key),
        ).fetchone()

        if participant_row is None:
            participant_id = _create_participant(
                connection,
                event_row=event_row,
                request=request,
                name_key=name_key,
                timestamp=timestamp,
            )
        else:
            _verify_returning_participant(
                request.password,
                participant_row["password_hash"],
            )
            participant_id = int(participant_row["id"])

        connection.execute(
            """
            INSERT INTO participant_sessions (
                token_hash,
                participant_id,
                created_at,
                last_used_at
            )
            VALUES (?, ?, ?, NULL)
            """,
            (
                hash_edit_token(edit_token),
                participant_id,
                timestamp,
            ),
        )

    return ParticipantJoinResult(
        participant_id=participant_id,
        edit_token=edit_token,
    )


def _create_participant(
    connection,
    *,
    event_row,
    request: ParticipantJoin,
    name_key: str,
    timestamp: str,
) -> int:
    dates = json.loads(event_row["dates"])
    slots_per_day = (
        event_row["day_end_minute"] - event_row["day_start_minute"]
    ) // event_row["slot_minutes"]
    availability = "0" * (len(dates) * slots_per_day)
    password_hash = (
        hash_password(request.password)
        if request.password is not None
        else None
    )

    cursor = connection.execute(
        """
        INSERT INTO participants (
            event_id,
            name,
            name_key,
            password_hash,
            availability,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_row["id"],
            request.name,
            name_key,
            password_hash,
            availability,
            timestamp,
        ),
    )
    participant_id = cursor.lastrowid
    if participant_id is None:
        raise RuntimeError("created participant has no identifier")

    connection.execute(
        """
        UPDATE events
        SET revision = revision + 1,
            updated_at = ?
        WHERE id = ?
        """,
        (timestamp, event_row["id"]),
    )
    return int(participant_id)


def _verify_returning_participant(
    supplied_password: str | None,
    password_hash: str | None,
) -> None:
    if password_hash is None:
        return
    if supplied_password is None or not verify_password(
        supplied_password,
        password_hash,
    ):
        raise InvalidParticipantPasswordError()


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
