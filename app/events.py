"""SQLite persistence operations for events."""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .db import connect
from .models import EventCreate, EventResponse, ParticipantResponse

MAX_SLUG_ATTEMPTS = 5


@dataclass(frozen=True)
class EventRecord:
    """Event values read from SQLite."""

    slug: str
    name: str
    schedule_kind: Literal["dates", "weekdays"]
    dates: list[str]
    day_start_minute: int
    day_end_minute: int
    slot_minutes: Literal[15, 30, 60]
    timezone: str
    revision: int
    created_at: str
    updated_at: str

    @property
    def slot_count(self) -> int:
        slots_per_day = (
            self.day_end_minute - self.day_start_minute
        ) // self.slot_minutes
        return len(self.dates) * slots_per_day

    def to_response(self) -> EventResponse:
        return EventResponse(
            **self.__dict__,
            slot_count=self.slot_count,
        )


def create_event(
    database_path: Path | str,
    event: EventCreate,
    *,
    slug_factory: Callable[[], str] | None = None,
) -> EventRecord:
    """Insert an event with a collision-resistant public slug."""
    create_slug = slug_factory or _generate_slug
    timestamp = _utc_timestamp()

    for _attempt in range(MAX_SLUG_ATTEMPTS):
        slug = create_slug()
        try:
            with connect(database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO events (
                        slug,
                        name,
                        schedule_kind,
                        dates,
                        day_start_minute,
                        day_end_minute,
                        slot_minutes,
                        timezone,
                        revision,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        slug,
                        event.name,
                        event.schedule_kind,
                        json.dumps(event.dates, separators=(",", ":")),
                        event.day_start_minute,
                        event.day_end_minute,
                        event.slot_minutes,
                        event.timezone,
                        timestamp,
                        timestamp,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM events WHERE slug = ?",
                    (slug,),
                ).fetchone()
        except sqlite3.IntegrityError as error:
            if "events.slug" in str(error):
                continue
            raise

        if row is None:
            raise RuntimeError("created event could not be read")
        return _event_from_row(row)

    raise RuntimeError("could not generate a unique event slug")


def get_event(
    database_path: Path | str,
    slug: str,
) -> EventRecord | None:
    """Return an event by public slug."""
    with connect(database_path, existing=True) as connection:
        row = connection.execute(
            "SELECT * FROM events WHERE slug = ?",
            (slug,),
        ).fetchone()
    return _event_from_row(row) if row is not None else None


def list_event_participants(
    database_path: Path | str,
    slug: str,
) -> list[ParticipantResponse]:
    """Return public participants for an event in insertion order."""
    with connect(database_path, existing=True) as connection:
        rows = connection.execute(
            """
            SELECT participants.id, participants.name, participants.availability
            FROM participants
            JOIN events ON events.id = participants.event_id
            WHERE events.slug = ?
            ORDER BY participants.id
            """,
            (slug,),
        ).fetchall()
    return [ParticipantResponse(**dict(row)) for row in rows]


def _event_from_row(row: sqlite3.Row) -> EventRecord:
    return EventRecord(
        slug=row["slug"],
        name=row["name"],
        schedule_kind=row["schedule_kind"],
        dates=json.loads(row["dates"]),
        day_start_minute=row["day_start_minute"],
        day_end_minute=row["day_end_minute"],
        slot_minutes=row["slot_minutes"],
        timezone=row["timezone"],
        revision=row["revision"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _generate_slug() -> str:
    return secrets.token_urlsafe(9)


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
