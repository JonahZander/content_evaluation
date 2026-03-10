# Codebase Walkthrough

This document is a fast map for understanding the current implementation and for reviewing changes without loading the entire repository at once.

## Top-Level Overview

The system is a monorepo with two application surfaces:

- `apps/web`
  - Next.js review workbench
  - Shows the source text on the left and anchored comment threads on the right
  - Handles reviewer replies, standalone comments, review-state actions, and export buttons
- `services/api`
  - FastAPI backend in Python 3.12
  - Accepts runs from URL, pasted text, or uploaded `.txt` / `.md`
  - Normalizes content, queues the run, processes it in a worker, and stores results

The main product loop is:

1. The user submits content from the web app.
2. The API creates a queued run and persists a `run_job`.
3. The worker claims the job and runs the analysis pipeline.
4. Findings become anchored comments, summary data, and run events.
5. The web app refreshes from the run API and event stream.
6. The reviewer replies to comments, marks agent comments accepted/rejected/uncertain, or exports the run.

## How the Code Is Organized

### Frontend

The frontend entrypoint is:

- `apps/web/app/page.tsx`

The main workbench coordinator is:

- `apps/web/src/components/ReviewWorkbench.tsx`

That file owns:

- run submission
- live refresh through SSE
- local UI state for replies, selection drafts, and inline comment editing
- refresh-after-mutation behavior

The presentational pieces live in:

- `apps/web/src/components/review/ReviewHero.tsx`
- `apps/web/src/components/review/ReviewToolbar.tsx`
- `apps/web/src/components/review/DocumentPane.tsx`
- `apps/web/src/components/review/CommentRail.tsx`
- `apps/web/src/components/review/ConnectorCanvas.tsx`
- `apps/web/src/components/review/RunMetrics.tsx`
- `apps/web/src/components/review/SelectionBanner.tsx`

The browser API contract lives in:

- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/types.ts`

Use those two files when reviewing frontend/backend contract changes.

### Backend

The backend HTTP entrypoint is:

- `services/api/src/content_evaluation/api/main.py`

The service container and runtime wiring live in:

- `services/api/src/content_evaluation/api/dependencies.py`
- `services/api/src/content_evaluation/config.py`

The domain models and enums live in:

- `services/api/src/content_evaluation/domain/models.py`
- `services/api/src/content_evaluation/domain/exceptions.py`

The repositories live in:

- `services/api/src/content_evaluation/repositories/base.py`
- `services/api/src/content_evaluation/repositories/in_memory.py`
- `services/api/src/content_evaluation/repositories/postgres.py`

The orchestration layer lives in:

- `services/api/src/content_evaluation/services/orchestration.py`
- `services/api/src/content_evaluation/services/worker.py`
- `services/api/src/content_evaluation/services/comments.py`
- `services/api/src/content_evaluation/services/exporting.py`
- `services/api/src/content_evaluation/services/normalization.py`
- `services/api/src/content_evaluation/services/anchors.py`

The external provider adapters live in:

- `services/api/src/content_evaluation/providers/openai/`
- `services/api/src/content_evaluation/providers/tavily/`
- `services/api/src/content_evaluation/providers/extraction/`
- `services/api/src/content_evaluation/providers/mock/`

## Request and Run Lifecycle

### Run creation

Start here:

- `POST /api/v1/runs` in `api/main.py`

That route:

1. validates JSON or file input
2. creates a run record through the orchestrator
3. enqueues a `RunJob`
4. returns immediately

### Run processing

Continue here:

- `services/api/src/content_evaluation/services/worker.py`

The worker:

1. polls the repository for queued jobs
2. claims one job
3. calls `RunOrchestrator.process_run(...)`
4. marks the job completed, failed, or requeued

### Analysis pipeline

The main backend behavior is in:

- `services/api/src/content_evaluation/services/orchestration.py`

Review this file for:

- source resolution
- normalization
- similarity search
- per-category analysis
- anchor creation
- agent comment creation
- summary scoring
- run event logging

### Review mutations

Human review actions are handled by:

- `services/api/src/content_evaluation/services/comments.py`

That is the file to review when checking:

- who can edit or delete comments
- who can reply
- which comments can receive review-state updates

### Export behavior

Exports are built by:

- `services/api/src/content_evaluation/services/exporting.py`

Review this file when checking:

- Markdown export structure
- JSON export schema stability
- whether replies, review states, and anchor references are preserved

## How to Review the Code

Use this order when doing a serious review.

### 1. Start with contracts

Read:

- `apps/web/src/lib/types.ts`
- `services/api/src/content_evaluation/domain/models.py`
- `services/api/src/content_evaluation/api/schemas.py`

This tells you:

- what a run looks like
- how anchors and comments are represented
- which fields are exchanged over the API

### 2. Review the main user flow

Read:

- `apps/web/src/components/ReviewWorkbench.tsx`
- `services/api/src/content_evaluation/api/main.py`
- `services/api/src/content_evaluation/services/orchestration.py`

This gives you the end-to-end path from submit to rendered review state.

### 3. Check the async boundaries

Read:

- `services/api/src/content_evaluation/services/worker.py`
- `services/api/src/content_evaluation/repositories/base.py`
- `services/api/src/content_evaluation/repositories/postgres.py`

Focus on:

- queue semantics
- retry behavior
- run state transitions
- persistence guarantees

### 4. Check reviewer permissions and safety rules

Read:

- `services/api/src/content_evaluation/services/comments.py`
- `apps/web/src/components/review/CommentRail.tsx`

Focus on:

- agent comments being immutable
- human comments being editable/deletable
- review-state actions only applying to agent comments

### 5. Check the UI linkage model

Read:

- `apps/web/src/components/review/DocumentPane.tsx`
- `apps/web/src/components/review/CommentRail.tsx`
- `apps/web/src/components/review/ConnectorCanvas.tsx`

Focus on:

- anchor rendering
- hover behavior
- multiple comments on one anchor
- visual connector correctness

### 6. Check fallback and runtime mode behavior

Read:

- `services/api/src/content_evaluation/config.py`
- `services/api/src/content_evaluation/api/dependencies.py`
- `services/api/src/content_evaluation/providers/mock/providers.py`

Focus on:

- when the app uses mock providers
- when production should fail fast
- whether readiness reflects reality

### 7. Finish with tests

Backend tests:

- `services/api/tests/test_api.py`
- `services/api/tests/test_comments.py`
- `services/api/tests/test_config.py`
- `services/api/tests/test_exports.py`
- provider and normalization tests

Frontend tests:

- `apps/web/test/ReviewWorkbench.test.tsx`

The tests are currently strongest around:

- API flow
- comment permissions
- exports
- provider parsing
- core workbench rendering

## Review Checklist

When reviewing a change, explicitly ask:

- Does the change preserve the run, anchor, and comment data contracts?
- Does it keep the worker and repository behavior consistent?
- Does it accidentally reintroduce mock fallbacks in production-sensitive code?
- Does it preserve the left-text/right-comment linkage in the UI?
- Does it keep exports aligned with persisted state?
- Did the relevant docs change with the behavior?
- Did generated artifacts stay out of version control?

## Fast File Map

If you only have a few minutes:

- Product behavior: `docs/product/content-evaluation-platform.md`
- UI behavior: `docs/frontend/annotation-review-workbench.md`
- Pipeline behavior: `docs/backend/analysis-pipeline.md`
- Runtime rules: `services/api/src/content_evaluation/config.py`
- Main API: `services/api/src/content_evaluation/api/main.py`
- Main UI: `apps/web/src/components/ReviewWorkbench.tsx`
