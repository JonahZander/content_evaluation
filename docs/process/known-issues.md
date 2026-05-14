# Known Issues

This file is the curated record of what is still open: deferred findings from a March 2026 code review, additional findings from an April 2026 spot-check pass, intentional simplifications, and known rough edges. Items that were fixed are summarized in the "Fixed or Closed" section at the bottom rather than enumerated. Agents encountering surprising behavior should check here before debugging.

**Commits that fixed code-review items:** `bf3f456`, `2c85ee7`, `3ad2f5d`

---

## Intentional Simplifications

These are design choices, not bugs.

### Similarity agent is dormant scaffolding

The `similarity` agent is registered in `agents/registry.py` with `selectable=False` and `default_enabled=False`, so it does not appear in `agent_catalog()` and the frontend cannot enable it. Its overlap-research role has been absorbed by the `fact_check` agent (`fact_check/research_brief.md`, deep-research provider), which is the path that actually runs in practice.

If the similarity branch is reached anyway, the `ProviderKind.SEARCH` path in `services/orchestration.py` builds a query from the document title, calls the Tavily search provider, and returns a single `FindingPayload` with a hardcoded rationale and a confidence derived from the max provider score. **No LLM call is made on this branch.** The `similarity.md` instruction file is loaded into `_INSTRUCTION_TEXT` at module import but is not read at runtime.

The dead scaffolding (registry entry, `SIMILARITY` enum value, `SimilaritySearchProvider` interface and mock, `_score_from_result` helper, the `"similarity"` literal in the frontend `AgentCategory` union) is intentionally retained:

- Removing it requires updating ~17 orchestrator instantiations in `tests/test_langgraph_runtime.py` plus `test_orchestration_maintenance.py`, `test_revised_markdown_workflow.py`, and `test_normalization.py`.
- Removing the `AgentCategory.SIMILARITY` enum value would make any persisted artifact whose findings carry `category: "similarity"` un-deserializable by Pydantic on read.
- A full LLM-backed similarity / overlap chain (search-plan → retrieve → rank → summarize) remains a possible future improvement; if revived, the existing scaffolding is the natural seam.

### No authentication

The API has no auth, rate limiting, or CSRF protection. This is intentional for the local-first, single-user use case. Do not deploy to a shared environment without adding an auth layer first.

---

## Open Findings (Deferred, Not Fixed)

These findings from the March 2026 code review were not addressed in the current iteration. Do not assume they are bugs — they are known and intentionally deferred.

### Backend

| ID | File | Issue |
|----|------|-------|
| H5 | `providers/tavily/client.py` | Tavily API key is sent in the JSON request body. Limitation of the Tavily API contract. |

### Infrastructure

| ID | Issue |
|----|-------|

A handful of unresolved low-severity findings from the same review are still deferred. They were judged not worth tracking individually here; if they resurface as concrete bugs they will be re-filed on their own.

---

## 2026-04-23 Spot-Check Review

A second review pass over the full codebase surfaced four additional findings. None block the local-first, single-user use case; they are tracked here for future cleanup.

### Backend

| ID  | File | Issue |
|-----|------|-------|
| M25 | `services/comments.py` (`_find_comment`, `_find_reply`) | Looks up a comment/reply by id by iterating every artifact id and fetching each artifact. Tolerable today because artifacts are cached in process, but every cache miss turns one comment mutation into N Postgres round-trips. Replace with a `comment_id → artifact_id` map or an indexed lookup before the artifact set grows. |
| L29 | `api/main.py` (`handle_domain_errors`) | Returns `str(error)` straight to the client. Today's `ContentEvaluationError` subclasses carry sanitized messages, but the handler enforces nothing — any future raise that interpolates internal context (provider URLs, file paths, secrets) will leak it. Map exception types to fixed user-facing strings. |

### Frontend

| ID  | File | Issue |
|-----|------|-------|
| L30 | `src/lib/api.ts` (`fetchAgents`) | Only API function in the module without a `signal?: AbortSignal` parameter, so callers cannot abort it on unmount. Every other function in the file accepts and forwards a signal. |
| L31 | `src/lib/types.ts` vs `domain/models.py` | `ArtifactSummary` and `ArtifactReviewSummary` mark several fields as optional on the TypeScript side (`tl_dr?`, `word_count?`, `article_format?`, `reading_difficulty?`, `structural_completeness?`, etc.) that the Pydantic models always populate with non-null defaults (`""`, `0`, `default_factory=...`). Not a runtime bug — fields are always on the wire — but it forces unnecessary `?? ""` / `?.` checks in consumers and gives the type system nothing to enforce. Either drop the `?` on the TS side or make the backend `| None` to match intent. |

---

## Deferred Dependency Upgrades (pip-audit 2026-04-24)

A `pip-audit` sweep flagged 16 Python advisories. Eight were closed as patch-level bumps in commit `ae6780f`. The six remaining are tracked here as deliberately deferred.

### LangChain / LangGraph 1.x migration

Four advisories can only be closed by a cross-package major-version migration. The four move together because they share peer-dep constraints:

| Package | Current | Fix | Advisory | Role in the codebase |
|---------|---------|-----|----------|----------------------|
| `langgraph` | 0.6.11 | 1.0.10 | CVE-2026-28277 | State-graph runtime; `services/orchestration.py`, `providers/deep_research/` |
| `langgraph-checkpoint` | 3.0.1 | 4.0.0 | CVE-2026-27794 | Persistence layer for langgraph state |
| `langchain-openai` | 0.3.35 | 1.1.14 | GHSA-r7w7-9xr2-qq2r | OpenAI chat-model adapter; every analysis/fact-check/compression agent |
| `langchain-text-splitters` | 0.3.11 | 1.1.2 | GHSA-fv5p-p927-qmxr | Document chunking in deep-research + intake |

**Why it is a real migration, not a version bump.** LangGraph 1.0 was a framework rewrite (new `create_agent` API, middleware hooks like `HumanInTheLoopMiddleware`, reshaped state-graph semantics, different stream-message types). LangChain 1.x restructured message handling, tool-call parsing, and prompt interpolation. The existing agent registry, orchestration driver, LangChain provider client, and the ~17 orchestrator instantiations in `tests/test_langgraph_runtime.py` all need to migrate together.

**Effort estimate.** Half a day to two days.

### pytest 9.x bump

| Package | Current | Fix | Advisory |
|---------|---------|-----|----------|
| `pytest` | 8.4.2 | 9.0.3 | CVE-2025-71176 |

Dev-only dependency. The CVE is a local code-execution path during test collection — exploitable only by running the test suite against a malicious workspace, which is not part of any normal flow. pytest 9 dropped a few deprecated APIs (notably `pytest.warns` context-manager behavior and some plugin hooks) and typically needs small fixture rewrites to pass cleanly. Rides along with the LangChain 1.x migration or can be done independently as a ~30-minute cleanup.

### pip CVE without fix

| Package | Current | Advisory | Status |
|---------|---------|----------|--------|
| `pip` | 26.0.1 | CVE-2026-3219 | **No fix version published yet.** |

Nothing to do until upstream publishes a patched release. Will stay on the Dependabot alert list regardless.

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
| M7 | Legacy full-run orchestration path retired; full runs always use LangGraph. The `OrchestratorBackend.LEGACY` enum value is still defined for backward compatibility but is rejected at startup by Settings validation, so it is unreachable at runtime. |
| M8 | `_ensure_run_active` now uses a narrow repository `get_run_status()` lookup instead of loading full artifacts. |
| M9 | All inline content now defaults to markdown format. The earlier plain-text auto-detection was removed; pasted text, URL imports, and file uploads all resolve to markdown unless the file extension is `.txt`. |
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
