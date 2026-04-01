"""API tests."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from content_evaluation.api.dependencies import AppServices
from content_evaluation.api.main import app
from content_evaluation.config import Settings
from content_evaluation.domain.models import ArtifactSummary, RunMode


def _mock_settings() -> Settings:
    """Build settings pinned to mock mode regardless of local env files."""

    return Settings(
        app_env="test",
        database_url=None,
        analysis_provider_family="mock",
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key=None,
        tavily_api_key=None,
    )


def _wait_for_run_completion(client: TestClient, run_id: str) -> dict[str, object]:
    """Poll until the requested run completes."""

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed", "canceled"}:
            return payload
        time.sleep(0.05)

    raise AssertionError("Run did not complete before timeout")


def _accept_agent_comments(client: TestClient, run_payload: dict[str, object]) -> list[str]:
    """Accept all agent comments with suggestions in a completed run payload."""

    accepted_comment_ids: list[str] = []
    for thread in run_payload["threads"]:
        for comment in thread["comments"]:
            if comment["author_type"] != "agent" or not comment.get("suggestion"):
                continue
            review_response = client.patch(
                f"/api/v1/comments/{comment['id']}/review-state",
                json={"review_state": "accepted"},
            )
            assert review_response.status_code == 200
            assert review_response.json()["review_state"] == "accepted"
            accepted_comment_ids.append(comment["id"])
    return accepted_comment_ids


def _render_applied_markdown(diff_review: dict[str, object]) -> str:
    """Reconstruct the applied markdown from diff-review decisions."""

    original_lines = str(diff_review["original_markdown"]).splitlines()
    applied_lines: list[str] = []
    cursor = 0
    for item in sorted(
        diff_review["diff_items"],
        key=lambda diff: (diff["original_start_line"], diff["original_end_line"], diff["id"]),
    ):
        start = max(0, item["original_start_line"] - 1)
        end = max(start, item["original_end_line"])
        applied_lines.extend(original_lines[cursor:start])
        if item["decision"] == "accepted":
            applied_lines.extend(str(item["after_text"]).splitlines())
        else:
            applied_lines.extend(original_lines[start:end])
        cursor = end
    applied_lines.extend(original_lines[cursor:])
    return "\n".join(applied_lines).strip()


def test_api_run_flow_and_exports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a run, wait for completion, and export it."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
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
        assert {item["agent_id"] for item in run_payload["agent_plan"]} == {
            "fact_check",
            "ai_likelihood",
            "editorial",
        }
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


def test_generate_revised_markdown_requires_accepted_suggestions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject revised-markdown generation until at least one suggestion has been accepted."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
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

        generate_response = client.post(
            f"/api/v1/runs/{run_id}/revised-markdown",
            json={"mode": "surgical"},
        )

    assert generate_response.status_code == 400
    assert "Accept at least one agent suggestion" in generate_response.text


def test_revised_markdown_diff_review_and_apply_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate revised markdown, review its diff items, and apply the reviewed result."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
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
        accepted_comment_ids = _accept_agent_comments(client, run_payload)

        generate_response = client.post(
            f"/api/v1/runs/{run_id}/revised-markdown",
            json={"mode": "rewrite", "direction_prompt": "Lead with the strongest finding."},
        )
        assert generate_response.status_code == 200
        revised_payload = generate_response.json()
        assert revised_payload["revised_document"]["mode"] == "rewrite"
        assert revised_payload["revised_document"]["direction_prompt"] == "Lead with the strongest finding."
        assert set(revised_payload["revised_document"]["accepted_comment_ids"]) == set(accepted_comment_ids)
        assert revised_payload["diff_review"]["diff_items"]

        diff_items = revised_payload["diff_review"]["diff_items"]
        assert len(diff_items) >= 2
        decisions = [{"diff_id": diff_items[0]["id"], "decision": "accepted"}]
        update_response = client.patch(
            f"/api/v1/runs/{run_id}/revised-markdown/diff-review",
            json={"decisions": decisions},
        )
        assert update_response.status_code == 200
        updated_diff_review = update_response.json()["diff_review"]
        updated_diff_items = updated_diff_review["diff_items"]
        assert updated_diff_items[0]["decision"] == "accepted"
        assert any(item["decision"] == "pending" for item in updated_diff_items[1:])
        expected_applied_markdown = _render_applied_markdown(updated_diff_review)

        apply_response = client.post(f"/api/v1/runs/{run_id}/revised-markdown/apply")
        assert apply_response.status_code == 200
        applied_payload = apply_response.json()
        assert applied_payload["status"] == "completed"
        assert applied_payload["previous_draft_snapshot"] is not None
        assert applied_payload["previous_draft_snapshot"]["threads"]
        if applied_payload["threads"]:
            assert any(comment["category"] == "fact_check" for thread in applied_payload["threads"] for comment in thread["comments"])
            assert all(
                comment["document_revision_id"] != applied_payload["document"]["revision_id"]
                for thread in applied_payload["threads"]
                for comment in thread["comments"]
            )
        assert all(result["category"] in {"fact_check", "research"} for result in applied_payload["agent_results"])
        assert applied_payload["document"]["raw_content"] == expected_applied_markdown


def test_api_rejects_invalid_upload_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject unsupported file uploads."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            files={"file": ("draft.pdf", b"not text", "application/pdf")},
        )

    assert response.status_code == 415


def test_api_run_accepts_multipart_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """Accept multipart run creation with the same run options as JSON submissions."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            data={
                "title": "Uploaded draft",
                "selected_agents": ["ai_likelihood", "editorial"],
                "persistence_mode": "session",
                "include_debug_trace": "true",
            },
            files={"file": ("draft.md", b"Alpha paragraph.\n\nBeta paragraph.", "text/markdown")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["source_type"] == "file"
    assert payload["source"]["source_label"] == "draft.md"
    assert payload["source"]["title"] == "Uploaded draft"
    assert payload["run_config"]["selected_agents"] == ["ai_likelihood", "editorial"]
    assert payload["run_config"]["persistence_mode"] == "session"
    assert payload["run_config"]["include_debug_trace"] is True


def test_artifact_summary_rejects_out_of_range_scores() -> None:
    """Reject scores outside the 0-100 range."""

    with pytest.raises(ValidationError):
        ArtifactSummary(
            overall_score=-1,
            verdict="ok",
            novelty_score=0.5,
            ai_likelihood=0.4,
        )

    with pytest.raises(ValidationError):
        ArtifactSummary(
            overall_score=101,
            verdict="ok",
            novelty_score=0.5,
            ai_likelihood=0.4,
        )


def test_ready_endpoint_reports_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return readiness data for local mock mode."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["processing_mode"] == "mock"


def test_run_events_stream_in_completion_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stream run events until completion."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
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


def test_preview_source_returns_normalized_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preview a source before queueing analysis."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sources/preview",
            json={
                "source_type": "url",
                "source_label": "https://example.com/post",
                "url": "https://example.com/post",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "example.com/post"
    assert payload["blocks"]


def test_api_returns_404_for_unknown_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return 404 for a run ID that does not exist."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_append_agents_queues_additional_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Queue additive analysis on a terminal artifact through the API."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "source_type": "text",
                "source_label": "Draft",
                "title": "Draft",
                "text": "This draft helps editors assess content.\n\nIt repeats itself in places.",
                "selected_agents": ["ai_likelihood"],
            },
        )
        assert response.status_code == 200
        run_id = response.json()["artifact_id"]
        _wait_for_run_completion(client, run_id)

        append_response = client.post(
            f"/api/v1/runs/{run_id}/agents",
            json={"selected_agents": ["editorial"]},
        )
        assert append_response.status_code == 200
        assert append_response.json()["status"] == "queued"

        run_payload = _wait_for_run_completion(client, run_id)
        assert run_payload["status"] == "completed"
        assert {item["agent_id"] for item in run_payload["agent_results"]} >= {
            "ai_likelihood",
            "fact_check",
            "editorial",
        }
        assert run_payload["run_config"]["selected_agents"] == ["ai_likelihood", "editorial"]


def test_append_agents_rejects_completed_fact_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse to rerun fact-check once it has already completed."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "source_type": "text",
                "source_label": "Draft",
                "title": "Draft",
                "text": "This draft helps editors assess content.\n\nIt repeats itself in places.",
                "selected_agents": ["fact_check"],
            },
        )
        assert response.status_code == 200
        run_id = response.json()["artifact_id"]
        run_payload = _wait_for_run_completion(client, run_id)
        assert {item["agent_id"] for item in run_payload["agent_results"]} >= {"fact_check"}

        append_response = client.post(
            f"/api/v1/runs/{run_id}/agents",
            json={"selected_agents": ["fact_check"]},
        )

    assert append_response.status_code == 400
    assert "No additional agents are available to run for this artifact." in append_response.text


def test_append_agents_rejects_active_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject additive analysis while the artifact is still active."""

    services = AppServices(_mock_settings())

    async def slow_process_run(artifact_id: object, input_data: object, **_: object) -> None:
        del artifact_id
        del input_data
        await asyncio.sleep(0.2)

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: services)
    monkeypatch.setattr(services.orchestrator, "process_run", slow_process_run)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "source_type": "text",
                "source_label": "Draft",
                "title": "Draft",
                "text": "This draft helps editors assess content.\n\nIt repeats itself in places.",
                "selected_agents": ["ai_likelihood"],
            },
        )
        assert response.status_code == 200
        run_id = response.json()["artifact_id"]

        append_response = client.post(
            f"/api/v1/runs/{run_id}/agents",
            json={"selected_agents": ["editorial"]},
        )

    assert append_response.status_code == 400
    assert "only available after a run has finished" in append_response.text


def test_research_endpoint_queues_targeted_follow_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Queue targeted research and persist the prompt as a comment reply."""

    services = AppServices(_mock_settings())
    original_process_run = services.orchestrator.process_run

    async def wrapped_process_run(artifact_id: object, input_data: object, **kwargs: object) -> None:
        if getattr(input_data, "mode", None) is RunMode.RESEARCH:
            await asyncio.sleep(0.2)
        await original_process_run(artifact_id, input_data, **kwargs)

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: services)
    monkeypatch.setattr(services.orchestrator, "process_run", wrapped_process_run)

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
        fact_check_comment = next(
            comment
            for thread in run_payload["threads"]
            for comment in thread["comments"]
            if comment["category"] == "fact_check"
        )

        research_response = client.post(
            f"/api/v1/runs/{run_id}/research",
            json={
                "prompt": "Verify the primary claim in this section.",
                "comment_id": fact_check_comment["id"],
            },
        )

        assert research_response.status_code == 200
        assert research_response.json()["status"] == "queued"

        final_payload = _wait_for_run_completion(client, run_id)
        research_comments = [
            comment
            for thread in final_payload["threads"]
            for comment in thread["comments"]
            if comment["category"] == "research"
        ]
        assert research_comments
        assert any(result["agent_id"] == "research" for result in final_payload["agent_results"])
        updated_fact_check_comment = next(
            comment
            for thread in final_payload["threads"]
            for comment in thread["comments"]
            if comment["id"] == fact_check_comment["id"]
        )
        assert updated_fact_check_comment["replies"]
        assert updated_fact_check_comment["replies"][0]["body"] == "Verify the primary claim in this section."


def test_api_returns_422_for_non_json_non_file_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return 422 when neither JSON nor file upload is provided."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post("/api/v1/runs", content=b"not json", headers={"content-type": "text/plain"})

    assert response.status_code == 422


def test_cancel_run_stops_inflight_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancel a running job through the API."""

    services = AppServices(_mock_settings())

    async def slow_process_run(artifact_id: object, input_data: object) -> None:
        del artifact_id
        del input_data
        await asyncio.sleep(0.2)

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: services)
    monkeypatch.setattr(services.orchestrator, "process_run", slow_process_run)

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

        cancel_response = client.post(f"/api/v1/runs/{run_id}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "canceled"

        run_payload = _wait_for_run_completion(client, run_id)
        assert run_payload["status"] == "canceled"


def test_generate_revised_markdown_requires_accepted_suggestions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject revised-markdown generation until an agent suggestion is accepted."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "source_type": "text",
                "source_label": "Draft",
                "title": "Draft",
                "text": "Alpha paragraph.\n\nBeta paragraph.",
                "selected_agents": ["editorial"],
            },
        )
        assert response.status_code == 200
        run_id = response.json()["artifact_id"]
        _wait_for_run_completion(client, run_id)

        revised_response = client.post(
            f"/api/v1/runs/{run_id}/revised-markdown",
            json={"mode": "surgical"},
        )

    assert revised_response.status_code == 400
    assert "Accept at least one agent suggestion" in revised_response.text


def test_api_generates_and_applies_revised_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate revised markdown, review the diffs, and promote the document."""

    monkeypatch.setattr("content_evaluation.api.main.build_services", lambda: AppServices(_mock_settings()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "source_type": "text",
                "source_label": "Draft",
                "title": "Draft",
                "text": "Alpha paragraph.\n\nBeta paragraph.",
                "selected_agents": ["editorial"],
            },
        )
        assert response.status_code == 200
        run_id = response.json()["artifact_id"]

        run_payload = _wait_for_run_completion(client, run_id)
        comment_id = run_payload["threads"][0]["comments"][0]["id"]
        review_response = client.patch(
            f"/api/v1/comments/{comment_id}/review-state",
            json={"review_state": "accepted"},
        )
        assert review_response.status_code == 200

        revised_response = client.post(
            f"/api/v1/runs/{run_id}/revised-markdown",
            json={"mode": "rewrite", "direction_prompt": "Lead with the strongest finding."},
        )
        assert revised_response.status_code == 200
        revised_payload = revised_response.json()
        assert revised_payload["revised_document"] is not None
        assert revised_payload["diff_review"] is not None
        assert revised_payload["revised_document"]["mode"] == "rewrite"
        assert revised_payload["revised_document"]["direction_prompt"] == "Lead with the strongest finding."
        diff_items = revised_payload["diff_review"]["diff_items"]
        assert diff_items

        diff_review_response = client.patch(
            f"/api/v1/runs/{run_id}/revised-markdown/diff-review",
            json={
                "decisions": [
                    {"diff_id": item["id"], "decision": "accepted"}
                    for item in diff_items
                ]
            },
        )
        assert diff_review_response.status_code == 200

        apply_response = client.post(f"/api/v1/runs/{run_id}/revised-markdown/apply")
        assert apply_response.status_code == 200
        applied_payload = apply_response.json()
        assert applied_payload["document"] is not None
        assert all(result["category"] in {"fact_check", "research"} for result in applied_payload["agent_results"])
        assert applied_payload["agent_plan"] == []
        assert applied_payload["summary"] is None
        assert applied_payload["review_summary"] is None
