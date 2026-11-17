"""FastAPI application factory and foundational health routes."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse

from .db import (
    DatabaseNotReadyError,
    check_readiness,
    initialize_database,
    resolve_database_path,
)
from .events import create_event, get_event, list_event_participants
from .models import EventCreate, EventCreated, EventDetailResponse
from .scheduling import group_counts

LOGGER = logging.getLogger(__name__)

ROOT_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Huddle App Lite</title>
</head>
<body>
  <main>
    <h1>Huddle App Lite</h1>
    <p>The application foundation is running.</p>
  </main>
</body>
</html>
"""


def create_app(database_path: Path | str | None = None) -> FastAPI:
    """Create an application whose database is initialized during startup."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_path = resolve_database_path(database_path)
        application.state.database_path = resolved_path
        try:
            initialize_database(resolved_path)
        except (DatabaseNotReadyError, OSError, sqlite3.Error):
            LOGGER.exception(
                "Database initialization failed; readiness will remain unavailable"
            )
        yield

    application = FastAPI(
        title="Huddle App Lite",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        return ROOT_PAGE

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get(
        "/readyz",
        response_model=None,
        responses={503: {"description": "Database or schema is not ready"}},
    )
    async def readiness() -> dict[str, str] | JSONResponse:
        try:
            check_readiness(application.state.database_path)
        except (DatabaseNotReadyError, OSError, sqlite3.Error):
            return JSONResponse(status_code=503, content={"status": "not ready"})
        return {"status": "ready"}

    @application.post(
        "/api/events",
        response_model=EventCreated,
        status_code=status.HTTP_201_CREATED,
    )
    def create_event_route(request: EventCreate) -> EventCreated:
        event = create_event(application.state.database_path, request)
        return EventCreated(slug=event.slug)

    @application.get(
        "/api/events/{slug}",
        response_model=EventDetailResponse,
    )
    def get_event_route(slug: str) -> EventDetailResponse:
        event = get_event(application.state.database_path, slug)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="event not found",
            )

        participants = list_event_participants(
            application.state.database_path,
            slug,
        )
        free_counts = group_counts(
            [participant.availability for participant in participants],
            event.slot_count,
        )
        return EventDetailResponse(
            event=event.to_response(),
            participants=participants,
            free_counts=free_counts,
            version=event.revision,
        )

    return application


app = create_app()
