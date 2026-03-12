"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sse_starlette.sse import EventSourceResponse

from content_evaluation.api.dependencies import (
    AppServices,
    build_services,
    get_comment_service,
    get_run_repository,
    get_services,
)
from content_evaluation.api.schemas import (
    CreateCommentRequest,
    CreateReplyRequest,
    CreateRunRequest,
    ImportArtifactRequest,
    PreviewSourceRequest,
    UpdateCommentRequest,
    UpdateReviewStateRequest,
)
from content_evaluation.domain.exceptions import ContentEvaluationError, NotFoundError
from content_evaluation.domain.models import AnalysisArtifact, ArtifactDocument, RunInput, RunJob, SourceType
from content_evaluation.logging import configure_logging, request_logging_middleware
from content_evaluation.repositories.base import RunRepository
from content_evaluation.repositories.postgres import PostgresRunRepository
from content_evaluation.services.comments import CommentService
from content_evaluation.services.exporting import build_json_export, build_markdown_export, build_todo_export

UploadFileInput = Annotated[UploadFile | None, File()]
ServicesDependency = Annotated[AppServices, Depends(get_services)]
RepositoryDependency = Annotated[RunRepository, Depends(get_run_repository)]
CommentServiceDependency = Annotated[CommentService, Depends(get_comment_service)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize long-lived app services."""

    configure_logging()
    services = build_services()
    app.state.services = services
    if isinstance(services.repository, PostgresRunRepository):
        await services.repository.initialize()
    await services.start()
    yield
    await services.stop()


app = FastAPI(title="Content Evaluation API", version="0.3.0", lifespan=lifespan)
app.middleware("http")(request_logging_middleware)

bootstrap_services = build_services()
app.add_middleware(
    CORSMiddleware,
    allow_origins=bootstrap_services.settings.cors_origins,
    allow_credentials=bootstrap_services.settings.app_env != "production",
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
)


@app.get("/health")
async def health(services: ServicesDependency) -> dict[str, str]:
    """Return a liveness status."""

    return {
        "status": "ok",
        "app_env": services.settings.app_env,
        "processing_mode": services.settings.runtime_mode.value,
    }


@app.get("/ready")
async def ready(services: ServicesDependency) -> JSONResponse:
    """Return a readiness report."""

    report = await services.readiness_report()
    status_code = status.HTTP_200_OK if report.status == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=report.model_dump(mode="json"), status_code=status_code)


@app.get("/api/v1/agents")
async def list_agents(services: ServicesDependency) -> object:
    """Return the available agent catalog."""

    return services.orchestrator.list_agents()


@app.post("/api/v1/runs")
async def create_run(
    http_request: Request,
    services: ServicesDependency,
    file: UploadFileInput = None,
) -> AnalysisArtifact:
    """Create one artifact from JSON or multipart input."""

    input_data = await _resolve_run_input(http_request, file, services)
    artifact = await services.orchestrator.create_run(input_data)
    await services.repository.enqueue_run_job(RunJob(artifact_id=artifact.artifact_id, input_data=input_data))
    return artifact


@app.post("/api/v1/sources/preview")
async def preview_source(payload: PreviewSourceRequest, services: ServicesDependency) -> ArtifactDocument:
    """Resolve and normalize one source without queueing a run."""

    return await services.orchestrator.preview_source_document(RunInput.model_validate(payload.model_dump()))


@app.post("/api/v1/artifacts/import")
async def import_artifact(payload: ImportArtifactRequest, services: ServicesDependency) -> AnalysisArtifact:
    """Import one saved artifact into the current backend session."""

    return await services.orchestrator.import_artifact(payload.artifact)


@app.get("/api/v1/runs/{run_id}")
async def get_run(run_id: UUID, repository: RepositoryDependency) -> AnalysisArtifact:
    """Return one artifact snapshot."""

    artifact = await repository.get_artifact(run_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return artifact


@app.post("/api/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: UUID, services: ServicesDependency) -> AnalysisArtifact:
    """Stop one queued or running artifact run."""

    artifact = await services.orchestrator.cancel_run(run_id)
    await services.worker.cancel_run(run_id)
    return artifact


@app.get("/api/v1/runs/{run_id}/events")
async def stream_run_events(run_id: UUID, repository: RepositoryDependency) -> EventSourceResponse:
    """Stream events for one artifact."""

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """Yield artifact events as SSE messages."""

        last_count = 0
        idle_loops = 0
        while True:
            artifact = await repository.get_artifact(run_id)
            if artifact is None:
                break
            events = artifact.events
            if len(events) > last_count:
                for event in events[last_count:]:
                    yield {"data": event.model_dump_json()}
                last_count = len(events)
                idle_loops = 0
            else:
                idle_loops += 1

            if artifact.status in {"completed", "failed", "canceled"} and idle_loops >= 2:
                break
            await asyncio.sleep(0.15)

    return EventSourceResponse(event_generator())


@app.post("/api/v1/comments")
async def create_comment(
    request: CreateCommentRequest,
    comments: CommentServiceDependency,
) -> object:
    """Create one human standalone comment."""

    return await comments.create_comment(
        request.artifact_id,
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
    comments: CommentServiceDependency,
) -> object:
    """Update one human standalone comment."""

    return await comments.update_comment(comment_id, request.body)


@app.delete("/api/v1/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(comment_id: str, comments: CommentServiceDependency) -> Response:
    """Delete one human standalone comment."""

    await comments.delete_comment(comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/comments/{comment_id}/replies")
async def create_reply(
    comment_id: str,
    request: CreateReplyRequest,
    comments: CommentServiceDependency,
) -> object:
    """Create one reply beneath a comment."""

    return await comments.add_reply(comment_id, request.body)


@app.delete("/api/v1/replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reply(reply_id: str, comments: CommentServiceDependency) -> Response:
    """Delete one human reply beneath a comment."""

    await comments.delete_reply(reply_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/api/v1/comments/{comment_id}/review-state")
async def update_review_state(
    comment_id: str,
    request: UpdateReviewStateRequest,
    comments: CommentServiceDependency,
) -> object:
    """Update one agent comment review state."""

    return await comments.set_review_state(comment_id, request.review_state)


@app.get("/api/v1/runs/{run_id}/export.md")
async def export_markdown(run_id: UUID, repository: RepositoryDependency) -> PlainTextResponse:
    """Return one Markdown export."""

    artifact = await repository.get_artifact(run_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return PlainTextResponse(build_markdown_export(artifact), media_type="text/markdown")


@app.get("/api/v1/runs/{run_id}/export.json")
async def export_json(run_id: UUID, repository: RepositoryDependency) -> Response:
    """Return one JSON export."""

    artifact = await repository.get_artifact(run_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return Response(build_json_export(artifact), media_type="application/json")


@app.get("/api/v1/runs/{run_id}/export.todo.md")
async def export_todo_markdown(run_id: UUID, repository: RepositoryDependency) -> PlainTextResponse:
    """Return one Markdown todo export."""

    artifact = await repository.get_artifact(run_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return PlainTextResponse(build_todo_export(artifact), media_type="text/markdown")


@app.exception_handler(ContentEvaluationError)
async def handle_domain_errors(_: object, error: ContentEvaluationError) -> Response:
    """Convert domain errors into HTTP responses."""

    status_code = 404 if isinstance(error, NotFoundError) else 400
    return Response(content=str(error), media_type="text/plain", status_code=status_code)


async def _resolve_run_input(
    http_request: Request,
    file: UploadFile | None,
    services: AppServices,
) -> RunInput:
    """Resolve incoming API input into one run input model."""

    if file is not None:
        return await _run_input_from_file(file, services)

    content_type = http_request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(status_code=422, detail="Either JSON input or file upload is required")
    payload = await http_request.json()
    request_data = CreateRunRequest.model_validate(payload)
    return RunInput.model_validate(request_data.model_dump())


async def _run_input_from_file(file: UploadFile, services: AppServices) -> RunInput:
    """Validate and convert one uploaded file into a run input."""

    file_name = file.filename or "upload"
    file_extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if file_extension not in {"txt", "md"}:
        raise HTTPException(status_code=415, detail="Only .txt and .md uploads are supported")

    content = await file.read()
    if len(content) > services.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload exceeds the configured size limit")

    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="Uploaded text must be valid UTF-8") from error

    return RunInput(
        source_type=SourceType.FILE,
        source_label=file_name,
        title=file_name,
        text=decoded,
    )
