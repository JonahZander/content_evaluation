# Known Issues

This file lists open findings from the 2026-03-13 code review, intentional simplifications, and known rough edges. Agents encountering surprising behavior should check here before debugging.

**Review source:** `docs/code-review-2026-03-13.md`
**Commits that fixed items:** `b28127b`, `ee15ca7`, `b924054`

---

## Intentional Simplifications

These are design choices, not bugs.

### Similarity agent is deterministic

The similarity agent uses Tavily search for retrieval and deterministic code-side synthesis. It does **not** send the `similarity.md` instruction file to an LLM. The `similarity.md` file exists and is loaded, but the current search node bypasses LLM analysis entirely.

Current stack: Tavily search → deterministic rationale/confidence in code → LangGraph eventing around the node.

This is known. A full LLM-backed research chain (search-plan → retrieve → rank → summarize) is a planned future improvement.

### No authentication

The API has no auth, rate limiting, or CSRF protection. This is intentional for the local-first, single-user use case. Do not deploy to a shared environment without adding an auth layer first.

---

## Open Findings (Deferred, Not Fixed)

These findings from the 2026-03-13 code review were not addressed in the current iteration. Do not assume they are bugs — they are known and intentionally deferred.

### Backend

| ID | File | Issue |
|----|------|-------|
| H5 | `providers/tavily/client.py` | Tavily API key is sent in the JSON request body. Limitation of the Tavily API contract. |
| H8 | Frontend tests | No tests for frontend error/failure paths. |
| M1 | `agents/registry.py` | `load_instruction_text()` uses synchronous `read_text()` on the async event loop. |
| M6 | `providers/extraction/client.py` | Fallback decision based on string matching in error messages (brittle). |
| M7 | `services/orchestration.py` | Stale artifact references in the legacy processing path. |
| M8 | `services/orchestration.py` | `_ensure_run_active` reads the full artifact from DB just to check `status`. |
| M9 | `services/orchestration.py` | Inline text sources are forced to `ContentFormat.MARKDOWN`. |
| M10 | `services/orchestration.py` | Full `raw_output` serialized into downstream agent prompts, inflating token counts. |
| M12 | `services/worker.py` | `ProviderError.retriable` flag is ignored at the worker level. |
| M15 | `config.py` | `lru_cache` on `get_settings()` prevents override in tests. |
| M16 | `api/dependencies.py` | Runtime mode compared via `.value == "live"` instead of `is RuntimeMode.LIVE`. |

### Frontend

| ID | File | Issue |
|----|------|-------|
| M17 | `ReviewWorkbench.tsx` / `api.ts` | `API_BASE_URL` duplicated in two files. Divergence would silently break SSE. |
| M19 | `ReviewWorkbench.tsx` | Weak sessionStorage type guards. |
| M20 | `ReviewWorkbench.tsx` | Full artifact serialized to sessionStorage on every state change. Can hit ~5MB quota for large documents. |
| M21 | `DocumentPane.tsx` | Resize handler fires without debounce. |
| M22 | `DocumentPane.tsx` | Connector paths go stale when anchor/comment refs mount or unmount. |
| M23 | `RunMetrics.tsx` | Shows "0%" when no data — implies a zero score rather than "not yet computed." |
| M24 | `api.ts` | No `AbortController` support. Stale responses can overwrite current state. |

### Infrastructure

| ID | Issue |
|----|-------|
| H10 | `.env` files not excluded from Docker web build context. |
| L26 | API Dockerfile does not copy `uv.lock`; builds are non-reproducible. |
| L27 | Both Dockerfiles run containers as root. |
| L28 | `.agents/` directory is untracked but not in `.gitignore`. |

All Low severity findings (L1–L28) from `docs/code-review-2026-03-13.md` remain open. Consult that document for the full list.

---

## Fixed in Recent Commits

These were critical or high findings that were resolved in commits `b28127b`, `ee15ca7`, and `b924054`.

| ID | What was fixed |
|----|---------------|
| C1 | SQL injection: now uses `psycopg.sql.Identifier` |
| C2 | Comment service broken for Postgres: now uses `list_artifact_ids()` |
| C3 | Double `build_services()` at import: single call in `lifespan()` |
| C4 | SSRF: `_validate_url()` with scheme allowlist and private IP blocking |
| H1 | No connection pooling: `AsyncConnectionPool(min_size=2, max_size=10)` |
| H2 | Dual-write consistency: Postgres-first writes, `deepcopy` on all reads |
| H3 | SSE stream no timeout: configurable `sse_stream_timeout_seconds` |
| H4 | Unbounded lock dict growth: `_artifact_locks.pop()` after run completes or cancels |
| H6 | Six frontend handlers with no error handling: all now have `try/catch` |
| H7 | Error body parsing: `parseJson` reads body before throwing |
| H9 | E2E test wrong assertion: now asserts `"Run log"` |
| M2 | Chat model re-instantiated per request: `_model_cache` per `(family, model_name)` |
| M3 | Prompt injection hardening: instructions moved to the system message and article content/upstream context now flow through a structured user payload |
| M4/M5 | httpx clients per request: created at `__init__` in all providers |
| M11 | Worker sequential: `asyncio.Semaphore(worker_max_concurrent_runs)` |
| M13 | FastAPI run creation now uses a typed JSON body route and a separate multipart route instead of manual JSON parsing |
| M14 | `ArtifactSummary.overall_score` now enforces `ge=0/le=100` |
| L14 | `SelectionDraft` duplicated: defined once in `src/lib/types.ts` |
| L25/M18 | 18+ `useState` hooks and missing `useCallback`: `useReducer` + stabilized callbacks |
