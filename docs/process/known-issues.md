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

### Infrastructure

| ID | Issue |
|----|-------|

Remaining unresolved low-severity findings from `docs/code-review-2026-03-13.md` are still deferred. Consult that document for the full historical list.

---

## Fixed or Closed

These findings have been resolved in prior commits or the current codebase state.

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
| H8 | Frontend error/failure paths now have focused workbench coverage; later stabilization commits expanded the test suite across run submission, preview/import, review mutations, and revised-markdown flows. |
| H9 | E2E test wrong assertion: now asserts `"Run log"` |
| M1 | Agent instructions are preloaded once in the registry; dispatch uses cached instruction text instead of synchronous file reads. |
| M2 | Chat model re-instantiated per request: `_model_cache` per `(family, model_name)` |
| M3 | Prompt injection hardening: instructions moved to the system message and article content/upstream context now flow through a structured user payload |
| M4/M5 | httpx clients per request: created at `__init__` in all providers |
| M6 | Extraction fallback now uses structured `ProviderError.fallback_eligible` metadata instead of string matching. |
| M7 | Legacy full-run orchestration path retired; settings now reject the removed legacy backend and full runs always use LangGraph. |
| M8 | `_ensure_run_active` now uses a narrow repository `get_run_status()` lookup instead of loading full artifacts. |
| M9 | Inline text input now preserves plain-text intent by default while keeping markdown-aware sources in markdown mode. |
| M10 | Downstream agent context is verified to exclude `raw_output`; tests assert the trimmed payload shape on the active LangGraph path. |
| M11 | Worker sequential: `asyncio.Semaphore(worker_max_concurrent_runs)` |
| M12 | Worker now respects `ProviderError.retriable` when requeueing or failing runs. |
| M13 | FastAPI run creation now uses a typed JSON body route and a separate multipart route instead of manual JSON parsing |
| M14 | `ArtifactSummary.overall_score` now enforces `ge=0/le=100` |
| M15 | Settings now use a resettable module-level singleton instead of `lru_cache`, so tests can override env-driven values. |
| M16 | Runtime-mode checks now compare directly against `RuntimeMode.LIVE`. |
| M17 | `API_BASE_URL` now lives in one shared frontend API client module and is reused by SSE paths. |
| M19/M20 | Session restore now uses strict v3 metadata-only storage with bounded draft recovery and fail-closed validation. |
| M21 | Stale finding closed: `DocumentPane` no longer uses the old resize-driven connector architecture, and session-storage writes are now coalesced to bounded metadata payloads. |
| M22 | Stale finding closed: connector overlay measurement is gone; inline highlights and paragraph-scoped rows replaced the old connector-path lifecycle. |
| M23 | Summary sub-scores (`novelty_score`, `ai_likelihood`) now support explicit null/unavailable values; the UI renders neutral placeholders and still renders real `0%`. |
| M24 | Mutation and review API calls now support `AbortSignal`, and workbench handlers guard against stale mutation responses overwriting newer state. |
| H10 | Web Docker builds now have an app-local `.dockerignore`, and the shared root context already excludes `.env*` files. |
| L14 | `SelectionDraft` duplicated: defined once in `src/lib/types.ts` |
| L26 | API Docker builds now copy `services/api/uv.lock` and use `uv sync --frozen` for reproducible installs. |
| L27 | Both Dockerfiles now drop root privileges before starting the app process. |
| L28 | Root `.gitignore` now ignores `.agents/*` scratch while explicitly keeping tracked repo-local skills. |
| L25/M18 | 18+ `useState` hooks and missing `useCallback`: `useReducer` + stabilized callbacks |
