"""Command-line entrypoint tests."""

import argparse

import pytest

from app import __main__ as command


def test_main_starts_uvicorn_with_explicit_bind(monkeypatch):
    invocation = {}

    def record_run(application, **options):
        invocation["application"] = application
        invocation["options"] = options

    monkeypatch.setattr(command.uvicorn, "run", record_run)

    exit_code = command.main(["--host", "0.0.0.0", "--port", "8123"])

    assert exit_code == 0
    assert invocation == {
        "application": "app.main:app",
        "options": {"host": "0.0.0.0", "port": 8123, "log_level": "info"},
    }


@pytest.mark.parametrize("port", ["0", "65536"])
def test_invalid_port_is_rejected(port):
    with pytest.raises(argparse.ArgumentTypeError):
        command.valid_port(port)
