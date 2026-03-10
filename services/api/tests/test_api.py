"""API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from content_evaluation.api.dependencies import AppServices
from content_evaluation.api.main import app
from content_evaluation.config import Settings


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
        run_id = response.json()["id"]

        run_response = client.get(f"/api/v1/runs/{run_id}")
        assert run_response.status_code == 200
        threads = run_response.json()["threads"]
        assert threads

        comment_id = threads[0]["comments"][0]["id"]
        reply_response = client.post(f"/api/v1/comments/{comment_id}/replies", json={"body": "Please keep the example."})
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
