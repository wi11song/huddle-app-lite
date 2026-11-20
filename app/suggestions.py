"""Read-only meeting suggestions composed from persisted availability."""

from __future__ import annotations

import json
from pathlib import Path

from .db import connect
from .models import SuggestionWindow, SuggestionsResponse
from .participants import EventNotFoundError
from .scheduling import (
    best_windows,
    duration_to_slots,
    earliest_common_slot,
)


class DurationExceedsDailyWindowError(ValueError):
    """Raised when a meeting cannot fit inside one event day."""


def get_suggestions(
    database_path: Path | str,
    event_slug: str,
    duration_minutes: int,
) -> SuggestionsResponse:
    """Return common and ranked windows from one consistent database snapshot."""
    with connect(database_path, existing=True) as connection:
        connection.execute("BEGIN")
        event_row = connection.execute(
            """
            SELECT
                dates,
                day_start_minute,
                day_end_minute,
                slot_minutes
            FROM events
            WHERE slug = ?
            """,
            (event_slug,),
        ).fetchone()
        if event_row is None:
            raise EventNotFoundError(event_slug)

        participant_rows = connection.execute(
            """
            SELECT participants.name, participants.availability
            FROM participants
            JOIN events ON events.id = participants.event_id
            WHERE events.slug = ?
            ORDER BY participants.id
            """,
            (event_slug,),
        ).fetchall()

    dates = json.loads(event_row["dates"])
    slots_per_day = (
        event_row["day_end_minute"] - event_row["day_start_minute"]
    ) // event_row["slot_minutes"]
    slot_count = len(dates) * slots_per_day
    needed_slots = duration_to_slots(
        duration_minutes,
        event_row["slot_minutes"],
    )
    if needed_slots > slots_per_day:
        raise DurationExceedsDailyWindowError(
            "duration exceeds the event's daily window"
        )

    if not participant_rows:
        return SuggestionsResponse(
            earliest_common_slot=None,
            best_windows=[],
        )

    availabilities = [row["availability"] for row in participant_rows]
    common_slot = earliest_common_slot(
        availabilities,
        slot_count,
        slots_per_day,
        needed_slots,
    )
    ranked_windows = best_windows(
        availabilities,
        slot_count,
        slots_per_day,
        needed_slots,
    )

    return SuggestionsResponse(
        earliest_common_slot=common_slot if common_slot >= 0 else None,
        best_windows=[
            SuggestionWindow(
                start_slot=start_slot,
                attendee_count=attendee_count,
                attendee_names=[
                    row["name"]
                    for row in participant_rows
                    if "0"
                    not in row["availability"][
                        start_slot : start_slot + needed_slots
                    ]
                ],
            )
            for start_slot, attendee_count in ranked_windows
        ],
    )
