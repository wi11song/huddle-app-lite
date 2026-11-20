"""Validated API models for events."""

from __future__ import annotations

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
WEEKDAY_POSITION = {weekday: index for index, weekday in enumerate(WEEKDAYS)}


class EventCreate(BaseModel):
    """Input accepted when creating an event."""

    name: str = Field(min_length=1, max_length=100)
    schedule_kind: Literal["dates", "weekdays"] = "dates"
    dates: list[str] = Field(min_length=1, max_length=14)
    day_start_minute: int = Field(ge=0, lt=1440)
    day_end_minute: int = Field(gt=0, le=1440)
    slot_minutes: Literal[15, 30, 60] = 15
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        timezone = value.strip()
        try:
            return ZoneInfo(timezone).key
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a recognized IANA name") from error

    @model_validator(mode="after")
    def validate_schedule(self) -> EventCreate:
        window_minutes = self.day_end_minute - self.day_start_minute
        if window_minutes <= 0:
            raise ValueError("day_start_minute must precede day_end_minute")
        if window_minutes % self.slot_minutes:
            raise ValueError("daily window must divide evenly into slots")

        if self.schedule_kind == "dates":
            normalized_dates = self._normalize_specific_dates()
        else:
            normalized_dates = self._normalize_weekdays()

        self.dates = normalized_dates
        return self

    def _normalize_specific_dates(self) -> list[str]:
        try:
            normalized = [date.fromisoformat(value).isoformat() for value in self.dates]
        except (TypeError, ValueError) as error:
            raise ValueError("dates must contain valid ISO dates") from error

        if len(set(normalized)) != len(normalized):
            raise ValueError("dates must not contain duplicates")
        return sorted(normalized)

    def _normalize_weekdays(self) -> list[str]:
        normalized = [
            value.strip().upper() if isinstance(value, str) else value
            for value in self.dates
        ]
        if any(value not in WEEKDAY_POSITION for value in normalized):
            raise ValueError("weekdays must use MON through SUN")
        if len(set(normalized)) != len(normalized):
            raise ValueError("weekdays must not contain duplicates")
        return sorted(normalized, key=WEEKDAY_POSITION.__getitem__)


class EventCreated(BaseModel):
    """Reference returned after creating an event."""

    slug: str


class EventResponse(BaseModel):
    """Public event fields returned to clients."""

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
    slot_count: int


class ParticipantResponse(BaseModel):
    """Public participant fields included in an event view."""

    id: int
    name: str
    availability: str


class ParticipantJoin(BaseModel):
    """Input accepted when joining or returning to an event."""

    name: str = Field(min_length=1, max_length=50)
    password: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class ParticipantJoined(BaseModel):
    """Participant identity and plaintext token returned only at issuance."""

    participant_id: int
    edit_token: str


class AvailabilityUpdate(BaseModel):
    """Complete participant availability bitstring."""

    availability: str = Field(
        min_length=1,
        max_length=1344,
        pattern=r"^[01]+$",
    )


class EventVersion(BaseModel):
    """Monotonic event revision used for lightweight polling."""

    version: int


class EventDetailResponse(BaseModel):
    """Event view shaped for later participant and heatmap support."""

    event: EventResponse
    participants: list[ParticipantResponse]
    free_counts: list[int]
    version: int
