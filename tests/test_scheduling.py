"""Unit tests for pure scheduling calculations."""

import pytest

from app.scheduling import (
    best_windows,
    duration_to_slots,
    earliest_common_slot,
    group_counts,
)


def test_group_counts_returns_participant_count_per_slot():
    availabilities = ["1010", "1100", "0011"]

    assert group_counts(availabilities, slot_count=4) == [2, 1, 2, 1]


def test_group_counts_without_participants_returns_zeroes():
    assert group_counts([], slot_count=4) == [0, 0, 0, 0]


@pytest.mark.parametrize(
    ("duration_minutes", "slot_minutes", "expected_slots"),
    [
        (15, 15, 1),
        (60, 15, 4),
        (61, 30, 3),
        (90, 60, 2),
    ],
)
def test_duration_to_slots_rounds_up(
    duration_minutes,
    slot_minutes,
    expected_slots,
):
    assert duration_to_slots(duration_minutes, slot_minutes) == expected_slots


@pytest.mark.parametrize(
    ("duration_minutes", "slot_minutes"),
    [(0, 15), (-1, 15), (30, 0), (30, -1)],
)
def test_duration_to_slots_rejects_non_positive_values(
    duration_minutes,
    slot_minutes,
):
    with pytest.raises(ValueError, match="must be positive"):
        duration_to_slots(duration_minutes, slot_minutes)


def test_earliest_common_slot_finds_first_complete_window():
    availabilities = [
        "10001110",
        "00001111",
        "01001110",
    ]

    assert (
        earliest_common_slot(
            availabilities,
            slot_count=8,
            slots_per_day=4,
            needed_slots=2,
        )
        == 4
    )


def test_earliest_common_slot_does_not_cross_day_boundary():
    availabilities = ["0110", "0110"]

    assert (
        earliest_common_slot(
            availabilities,
            slot_count=4,
            slots_per_day=2,
            needed_slots=2,
        )
        == -1
    )


def test_earliest_common_slot_returns_minus_one_without_participants():
    assert (
        earliest_common_slot(
            [],
            slot_count=4,
            slots_per_day=2,
            needed_slots=1,
        )
        == -1
    )


def test_earliest_common_slot_returns_minus_one_when_duration_exceeds_day():
    assert (
        earliest_common_slot(
            ["1111"],
            slot_count=4,
            slots_per_day=2,
            needed_slots=3,
        )
        == -1
    )


def test_best_windows_rank_attendance_then_earliest_start():
    availabilities = [
        "110110",
        "110011",
        "011110",
    ]

    assert best_windows(
        availabilities,
        slot_count=6,
        slots_per_day=3,
        needed_slots=2,
    ) == [(0, 2), (3, 2), (1, 1)]


def test_best_windows_still_return_partial_overlap_without_common_time():
    availabilities = ["1100", "0011"]

    assert (
        earliest_common_slot(
            availabilities,
            slot_count=4,
            slots_per_day=4,
            needed_slots=2,
        )
        == -1
    )
    assert best_windows(
        availabilities,
        slot_count=4,
        slots_per_day=4,
        needed_slots=2,
    ) == [(0, 1), (2, 1), (1, 0)]


def test_best_windows_exclude_cross_day_windows():
    assert best_windows(
        ["1111"],
        slot_count=4,
        slots_per_day=2,
        needed_slots=2,
        top=4,
    ) == [(0, 1), (2, 1)]


def test_best_windows_support_custom_result_limit():
    assert best_windows(
        ["1111"],
        slot_count=4,
        slots_per_day=4,
        needed_slots=1,
        top=2,
    ) == [(0, 1), (1, 1)]


@pytest.mark.parametrize(
    ("availabilities", "slot_count", "message"),
    [
        (["101"], 4, "length"),
        (["10x0"], 4, "only 0 and 1"),
        ([], -1, "slot_count"),
    ],
)
def test_group_counts_rejects_malformed_input(
    availabilities,
    slot_count,
    message,
):
    with pytest.raises(ValueError, match=message):
        group_counts(availabilities, slot_count)


@pytest.mark.parametrize(
    ("slot_count", "slots_per_day", "needed_slots", "message"),
    [
        (5, 2, 1, "complete days"),
        (4, 0, 1, "slots_per_day"),
        (4, 2, 0, "needed_slots"),
    ],
)
def test_suggestions_reject_invalid_schedule_shape(
    slot_count,
    slots_per_day,
    needed_slots,
    message,
):
    with pytest.raises(ValueError, match=message):
        earliest_common_slot(
            [],
            slot_count,
            slots_per_day,
            needed_slots,
        )
