"""Pure functions for availability counts and meeting suggestions."""

from __future__ import annotations

from collections.abc import Sequence


def duration_to_slots(duration_minutes: int, slot_minutes: int) -> int:
    """Return the number of slots needed to contain a meeting duration."""
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if slot_minutes <= 0:
        raise ValueError("slot_minutes must be positive")
    return (duration_minutes + slot_minutes - 1) // slot_minutes


def group_counts(
    availabilities: Sequence[str],
    slot_count: int,
) -> list[int]:
    """Count available participants at each slot."""
    _validate_availabilities(availabilities, slot_count)
    return [
        sum(availability[slot_index] == "1" for availability in availabilities)
        for slot_index in range(slot_count)
    ]


def earliest_common_slot(
    availabilities: Sequence[str],
    slot_count: int,
    slots_per_day: int,
    needed_slots: int,
) -> int:
    """Return the earliest all-participant window, or -1 when none fits."""
    _validate_schedule_shape(slot_count, slots_per_day, needed_slots)
    free_counts = group_counts(availabilities, slot_count)
    if not availabilities or needed_slots > slots_per_day:
        return -1

    participant_count = len(availabilities)
    consecutive_free_slots = 0

    for slot_index, free_count in enumerate(free_counts):
        if slot_index % slots_per_day == 0:
            consecutive_free_slots = 0

        if free_count == participant_count:
            consecutive_free_slots += 1
        else:
            consecutive_free_slots = 0

        if consecutive_free_slots == needed_slots:
            return slot_index - needed_slots + 1

    return -1


def best_windows(
    availabilities: Sequence[str],
    slot_count: int,
    slots_per_day: int,
    needed_slots: int,
    top: int = 3,
) -> list[tuple[int, int]]:
    """Return highest-attendance windows ordered by attendance then start."""
    _validate_schedule_shape(slot_count, slots_per_day, needed_slots)
    _validate_availabilities(availabilities, slot_count)
    if top < 0:
        raise ValueError("top must not be negative")
    if top == 0 or needed_slots > slots_per_day:
        return []

    windows: list[tuple[int, int]] = []
    for start_slot in range(slot_count):
        end_slot = start_slot + needed_slots
        day_end_slot = (start_slot // slots_per_day + 1) * slots_per_day
        if end_slot > day_end_slot or end_slot > slot_count:
            continue

        attendee_count = sum(
            "0" not in availability[start_slot:end_slot]
            for availability in availabilities
        )
        windows.append((start_slot, attendee_count))

    windows.sort(key=lambda window: (-window[1], window[0]))
    return windows[:top]


def _validate_schedule_shape(
    slot_count: int,
    slots_per_day: int,
    needed_slots: int,
) -> None:
    if slot_count < 0:
        raise ValueError("slot_count must not be negative")
    if slots_per_day <= 0:
        raise ValueError("slots_per_day must be positive")
    if needed_slots <= 0:
        raise ValueError("needed_slots must be positive")
    if slot_count % slots_per_day != 0:
        raise ValueError("slot_count must contain complete days")


def _validate_availabilities(
    availabilities: Sequence[str],
    slot_count: int,
) -> None:
    if slot_count < 0:
        raise ValueError("slot_count must not be negative")

    for availability in availabilities:
        if len(availability) != slot_count:
            raise ValueError("availability length must equal slot_count")
        if set(availability) - {"0", "1"}:
            raise ValueError("availability must contain only 0 and 1")
