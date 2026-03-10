"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from sse_starlette.sse import EventSourceResponse

from content_evaluation.api.dependencies import AppServices, build_services, get_comment_service, get_run_repository, get_services
from content_evaluation.api.schemas import (
    CreateCommentRequest,
    CreateReplyRequest,
    CreateRunRequest,
    UpdateCommentRequest,
    UpdateReviewStateRequest,
)
from content_evaluation.domain.exceptions import ContentEvaluationError, NotFoundError
from content_evaluation.domain.models import RunInput, RunMetadata, RunStatus, SourceType
from content_evaluation.repositories.base import RunRepository
from content_evaluation.repositories.postgres import PostgresRunRepository
from content_evaluation.services.comments import CommentService
from content_evaluation.services.exporting import build_json_export, build_markdown_export


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize long-lived app services."""

    services = build_services()
    app.state.services = services
    if isinstance(services.repository, PostgresRunRepository):
        await services.repository.initialize()
    yield


app = FastAPI(title="Content Evaluation API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return a health status."""

    return {"status": "ok"}


@app.post("/api/v1/runs")
async def create_run(
    background_tasks: BackgroundTasks,
    http_request: Request,
    file: UploadFile | None = File(default=None),
    services: AppServices = Depends(get_services),
) -> RunMetadata:
    """Create one run from JSON or multipart input."""

    input_data = await _resolve_run_input(http_request, file)
    run = await services.orchestrator.create_run(input_data)
    background_tasks.add_task(services.orchestrator.process_run, run.id, input_data)
    return run


@app.get("/api/v1/runs/{run_id}")
async def get_run(run_id: UUID, repository: RunRepository = Depends(get_run_repository)) -> object:
    """Return one full run detail."""

    detail = await repository.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return detail


@app.get("/api/v1/runs/{run_id}/events")
async def stream_run_events(run_id: UUID, repository: RunRepository = Depends(get_run_repository)) -> EventSourceResponse:
    """Stream events for one run."""

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """Yield run events as SSE messages."""

        last_count = 0
        idle_loops = 0
        while True:
            detail = await repository.get_run_detail(run_id)
            if detail is None:
                break
            events = detail.events
            if len(events) > last_count:
                for event in events[last_count:]:
                    yield {"event": "run_event", "data": event.model_dump_json()}
                last_count = len(events)
                idle_loops = 0
            else:
                idle_loops += 1

            if detail.run.status in (RunStatus.COMPLETED, RunStatus.FAILED) and idle_loops >= 2:
                break
            await asyncio.sleep(0.25)

    return EventSourceResponse(event_generator())


@app.post("/api/v1/comments")
async def create_comment(
    request: CreateCommentRequest,
    comments: CommentService = Depends(get_comment_service),
) -> object:
    """Create one human standalone comment."""

    return await comments.create_comment(
        request.run_id,
        request.body,
        request.anchor_id,
        block_id=request.block_id,
        start_offset=request.start_offset,
        end_offset=request.end_offset,
        quote=request.quote,
    )


@app.patch("/api/v1/comments/{comment_id}")
async def update_comment(
    comment_id: str,
    request: UpdateCommentRequest,
    comments: CommentService = Depends(get_comment_service),
) -> object:
    """Update one human standalone comment."""

    return await comments.update_comment(comment_id, request.body)


@app.delete("/api/v1/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, comments: CommentService = Depends(get_comment_service)) -> Response:
    """Delete one human standalone comment."""

    await comments.delete_comment(comment_id)
    return Response(status_code=204)


@app.post("/api/v1/comments/{comment_id}/replies")
async def create_reply(
    comment_id: str,
    request: CreateReplyRequest,
    comments: CommentService = Depends(get_comment_service),
) -> object:
    """Create one reply beneath a comment."""

    return await comments.add_reply(comment_id, request.body)


@app.patch("/api/v1/comments/{comment_id}/review-state")
async def update_review_state(
    comment_id: str,
    request: UpdateReviewStateRequest,
    comments: CommentService = Depends(get_comment_service),
) -> object:
    """Update one agent comment review state."""

    return await comments.set_review_state(comment_id, request.review_state)


@app.get("/api/v1/runs/{run_id}/export.md")
async def export_markdown(run_id: UUID, repository: RunRepository = Depends(get_run_repository)) -> PlainTextResponse:
    """Return one Markdown export."""

    detail = await repository.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return PlainTextResponse(build_markdown_export(detail), media_type="text/markdown")


@app.get("/api/v1/runs/{run_id}/export.json")
async def export_json(run_id: UUID, repository: RunRepository = Depends(get_run_repository)) -> Response:
    """Return one JSON export."""

    detail = await repository.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return Response(build_json_export(detail), media_type="application/json")


@app.exception_handler(ContentEvaluationError)
async def handle_domain_errors(_: object, error: ContentEvaluationError) -> Response:
    """Convert domain errors into HTTP responses."""

    status_code = 404 if isinstance(error, NotFoundError) else 400
    return Response(content=str(error), media_type="text/plain", status_code=status_code)


async def _resolve_run_input(http_request: Request, file: UploadFile | None) -> RunInput:
    """Resolve incoming API input into one run input model."""

    if file is not None:
        content = (await file.read()).decode("utf-8")
        return RunInput(source_type=SourceType.FILE, source_label=file.filename or "upload", title=file.filename, text=content)
    if "application/json" not in http_request.headers.get("content-type", ""):
        raise HTTPException(status_code=422, detail="Either JSON input or file upload is required")
    payload = await http_request.json()
    request_data = CreateRunRequest.model_validate(payload)
    return RunInput.model_validate(request_data.model_dump())
