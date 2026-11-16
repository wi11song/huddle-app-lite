"""Command-line entrypoint for ``python -m app``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn


def valid_port(value: str) -> int:
    """Parse and validate a TCP port."""
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Huddle App Lite")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=valid_port, default=8000)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    uvicorn.run(
        "app.main:app",
        host=options.host,
        port=options.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
