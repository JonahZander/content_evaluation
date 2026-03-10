"""API tests."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from content_evaluation.api.dependencies import AppServices
from content_evaluation.api.main import app
from content_evaluation.config import Settings


def _wait_for_run_completion(client: TestClient, run_id: str) -> dict[str, object]:
    """Poll until the requested run completes."""

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)

    raise AssertionError("Run did not complete before timeout")


def test_api_run_flow_and_exports() -> None:
    """Create a run, wait for completion, and export it."""

    app.state.services = AppServices(Settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "source_type": "text",
                "source_label": "Draft",
                "title": "Draft",
                "text": "This draft helps editors assess content.\n\nIt repeats itself in places.",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["artifact_id"]

        run_payload = _wait_for_run_completion(client, run_id)
        assert run_payload["status"] == "completed"
        threads = run_payload["threads"]
        assert threads

        comment_id = threads[0]["comments"][0]["id"]
        reply_response = client.post(
            f"/api/v1/comments/{comment_id}/replies", json={"body": "Please keep the example."}
        )
        assert reply_response.status_code == 200

        review_response = client.patch(
            f"/api/v1/comments/{comment_id}/review-state",
            json={"review_state": "accepted"},
        )
        assert review_response.status_code == 200
        assert review_response.json()["review_state"] == "accepted"

        markdown_export = client.get(f"/api/v1/runs/{run_id}/export.md")
        json_export = client.get(f"/api/v1/runs/{run_id}/export.json")
        assert markdown_export.status_code == 200
        assert json_export.status_code == 200


def test_api_rejects_invalid_upload_type() -> None:
    """Reject unsupported file uploads."""

    app.state.services = AppServices(Settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            files={"file": ("draft.pdf", b"not text", "application/pdf")},
        )

    assert response.status_code == 415


def test_ready_endpoint_reports_mock_mode() -> None:
    """Return readiness data for local mock mode."""

    app.state.services = AppServices(Settings())
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["processing_mode"] == "mock"


def test_run_events_stream_in_completion_order() -> None:
    """Stream run events until completion."""

    app.state.services = AppServices(Settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "source_type": "text",
                "source_label": "Draft",
                "title": "Draft",
                "text": "This draft helps editors assess content.\n\nIt repeats itself in places.",
            },
        )
        assert response.status_code == 200
        run_id = response.json()["artifact_id"]
        _wait_for_run_completion(client, run_id)

        with client.stream("GET", f"/api/v1/runs/{run_id}/events") as stream_response:
            payload = "".join(stream_response.iter_text())

    assert stream_response.status_code == 200
    assert '"status":"started"' in payload
    assert '"status":"completed"' in payload
