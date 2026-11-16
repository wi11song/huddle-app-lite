"""FastAPI application factory and foundational health routes."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from .db import (
    DatabaseNotReadyError,
    check_readiness,
    initialize_database,
    resolve_database_path,
)

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

    return application


app = create_app()
