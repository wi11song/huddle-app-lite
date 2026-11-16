"""Start the application against a temporary database and probe key pages."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def reserve_port() -> int:
    """Ask the operating system for an available loopback TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def stop_process(process: subprocess.Popen[str]) -> str:
    """Stop the application process and return its combined output."""
    if process.poll() is None:
        process.terminate()

    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()

    return output


def wait_for_url(
    url: str, timeout_seconds: float, process: subprocess.Popen[str]
) -> None:
    """Wait until a URL returns a successful HTTP response."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            output, _ = process.communicate()
            raise RuntimeError(
                f"application exited with status {return_code} while waiting "
                f"for {url}\n{output}"
            )

        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 300:
                    return
                last_error = RuntimeError(
                    f"{url} returned unexpected status {response.status}"
                )
        except OSError as error:
            last_error = error
        time.sleep(0.2)

    raise RuntimeError(f"{url} did not become ready: {last_error}")


def main() -> int:
    port = reserve_port()

    with tempfile.TemporaryDirectory(prefix="huddle-startup-") as temp_directory:
        environment = os.environ.copy()
        environment["HUDDLE_DB_PATH"] = str(Path(temp_directory) / "startup.db")

        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            wait_for_url(f"http://127.0.0.1:{port}/healthz", 10, process)
            wait_for_url(f"http://127.0.0.1:{port}/", 5, process)
        except Exception:
            if process.poll() is None:
                output = stop_process(process)
                if output:
                    print(output, file=sys.stderr)
            raise
        finally:
            if process.poll() is None:
                stop_process(process)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
