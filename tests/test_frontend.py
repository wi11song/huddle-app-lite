"""Static frontend routes and delivery-budget tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import STATIC_DIRECTORY, create_app


def test_create_page_loads_frontend_assets(tmp_path):
    with TestClient(create_app(tmp_path / "frontend.db")) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="event-form"' in response.text
    assert 'id="date-list"' in response.text
    assert 'src="/static/app.js"' in response.text
    assert 'href="/static/styles.css"' in response.text


def test_event_page_contains_join_and_share_shell(tmp_path):
    with TestClient(create_app(tmp_path / "event-page.db")) as client:
        response = client.get("/e/example-slug")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="share-link"' in response.text
    assert 'id="join-form"' in response.text
    assert 'id="participant-list"' in response.text
    assert 'id="availability-title"' in response.text
    assert 'id="availability-grid"' in response.text
    assert 'id="availability-status"' in response.text
    assert 'id="group-grid"' in response.text
    assert 'id="group-slot-detail"' in response.text
    assert 'id="group-refresh-status"' in response.text
    assert 'id="suggestions-form"' in response.text
    assert 'id="suggestion-duration"' in response.text
    assert 'id="earliest-title"' in response.text
    assert 'id="suggestion-list"' in response.text


def test_static_css_and_javascript_are_served_and_compressed(tmp_path):
    with TestClient(create_app(tmp_path / "assets.db")) as client:
        css_response = client.get("/static/styles.css")
        script_response = client.get(
            "/static/app.js",
            headers={"Accept-Encoding": "gzip"},
        )

    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")
    assert script_response.status_code == 200
    assert "javascript" in script_response.headers["content-type"]
    assert script_response.headers["content-encoding"] == "gzip"


def test_frontend_avoids_inner_html_for_dynamic_content():
    script = (STATIC_DIRECTORY / "app.js").read_text()

    assert ".innerHTML" not in script
    assert ".textContent" in script
    assert "localStorage.setItem" in script
    assert '"pointerdown"' in script
    assert '"pointermove"' in script
    assert "setTimeout(saveAvailability, 400)" in script
    assert '"X-Edit-Token"' in script
    assert "/version" in script
    assert "setInterval(pollEventVersion, 5000)" in script
    assert "/suggestions" in script
    assert "earliest_common_slot" in script
    assert "best_windows" in script


def test_frontend_page_weight_stays_below_budget():
    frontend_files = [
        STATIC_DIRECTORY / "index.html",
        STATIC_DIRECTORY / "event.html",
        STATIC_DIRECTORY / "styles.css",
        STATIC_DIRECTORY / "app.js",
    ]

    assert all(Path(file_path).is_file() for file_path in frontend_files)
    assert sum(file_path.stat().st_size for file_path in frontend_files) < 100_000


def test_missing_static_asset_returns_not_found(tmp_path):
    with TestClient(create_app(tmp_path / "missing-asset.db")) as client:
        response = client.get("/static/does-not-exist.js")

    assert response.status_code == 404
