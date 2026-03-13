# Code Review -- Content Evaluation

**Date:** 2026-03-13
**Scope:** Full codebase (21 commits on `main`)
**Backend:** ~15,400 lines Python (FastAPI + LangChain/LangGraph)
**Frontend:** ~9,000 lines TypeScript/React (Next.js)

---

## Executive Summary

The codebase is well-organized and demonstrates strong architectural thinking: clean domain models, protocol-based provider abstractions, declarative agent registry, and a clear frontend layering. For a solo-developed project at this stage, the code quality is high.

The review found **4 critical**, **10 high**, **24 medium**, and **28 low** severity findings across backend, frontend, and infrastructure. The most urgent items are:

1. SQL injection pattern in the Postgres repository
2. SSRF vulnerability in the extraction provider
3. Comment service is broken when using PostgreSQL persistence
4. Double `AppServices` construction at API startup
5. No error handling on six frontend mutation handlers
6. Docker images leak secrets and run as root

None of these are exploitable in the current local-first, single-user usage, but they become real risks the moment the application is deployed to a shared environment.

---

## Findings by Severity

### Critical

| # | Area | File | Line(s) | Issue |
|---|------|------|---------|-------|
| C1 | Backend | `repositories/postgres.py` | 190-199 | **SQL injection pattern.** `table` and `key_column` are f-string-interpolated into SQL. Current callers pass hardcoded strings, but the pattern is dangerous. Use `psycopg.sql.Identifier` for safe identifier interpolation. |
| C2 | Backend | `services/comments.py` | 143, 156 | **Comment service broken for Postgres.** `_find_comment` and `_find_reply` access the repository's private `_artifacts` dict via `getattr`. This only works with `InMemoryRunRepository`. With Postgres, artifacts not already in the in-memory cache will not be found, causing spurious `NotFoundError` on every comment mutation. |
| C3 | Backend | `api/main.py` | 60-70 | **Double `AppServices` construction.** `build_services()` is called at module import time (for CORS config) and again in `lifespan()`. Two independent service instances are created -- two workers, two repositories, two provider sets. The module-level instance is never shut down. |
| C4 | Backend | `providers/extraction/client.py` | 22-28 | **SSRF vulnerability.** User-supplied URLs are passed directly to `httpx.AsyncClient.get()` with no scheme allowlist, private IP blocking, or hostname validation. An attacker could reach internal services (e.g., `http://169.254.169.254/`, `http://localhost:5432/`). |

### High

| # | Area | File | Line(s) | Issue |
|---|------|------|---------|-------|
| H1 | Backend | `repositories/postgres.py` | 47, 73, 142, 197 | **No connection pooling.** Every repository method opens and closes a new `psycopg.AsyncConnection`. Under load, this overwhelms the database with connection churn. Use `psycopg_pool.AsyncConnectionPool`. |
| H2 | Backend | `repositories/postgres.py` | 53-64, 80-81, 153 | **Dual-write consistency bugs.** In-memory writes succeed before Postgres writes; no rollback on Postgres failure. `save_graph_checkpoint` skips `deepcopy`. `get_artifact` populates cache without `deepcopy`, allowing shared-reference mutations. |
| H3 | Backend | `api/main.py` | 147-173 | **SSE stream has no timeout.** If a run gets stuck, the connection polls `get_artifact()` indefinitely at 0.15s intervals, consuming a worker slot forever. |
| H4 | Backend | `services/orchestration.py` | 122, 1048-1051 | **Unbounded lock dictionary growth.** A new `asyncio.Lock` is created per artifact and never removed. Memory leak in long-running servers. |
| H5 | Backend | `providers/tavily/client.py` | 29-37 | **API key in JSON body.** The Tavily API key is sent in the request payload, where it can appear in logs, traces, and error serializations. |
| H6 | Frontend | `ReviewWorkbench.tsx` | 538-608 | **Six async handlers have no error handling.** `handleCreateComment`, `handleReply`, `handleDeleteReply`, `handleReviewState`, `handleSaveEdit`, `handleDeleteHumanComment` lack try/catch. Failed API calls produce unhandled promise rejections and leave the UI inconsistent. |
| H7 | Frontend | `api.ts` | 26-31 | **Error responses discard the body.** `parseJson` throws with only the HTTP status code. The backend's structured error message is never read, making failures opaque to both users and developers. |
| H8 | Frontend | `ReviewWorkbench.test.tsx` | -- | **No tests for error/failure paths.** Given H6, the unhandled error paths are also untested. |
| H9 | Frontend | `review-workbench.spec.ts` | 18 | **E2E test references wrong text.** Asserts `"Comment rail"` is visible, but `CommentRail.tsx` renders `"Run log"`. This assertion is either broken or matching unrelated text. |
| H10 | Infra | `.dockerignore` | -- | **`.env` files not excluded from Docker build context.** The web Dockerfile's `COPY . .` sends `.env` files into the builder layer. Even though they are not in the final stage, they persist in image history and can be extracted. |

### Medium

| # | Area | File | Line(s) | Issue |
|---|------|------|---------|-------|
| M1 | Backend | `agents/registry.py` | 164 | Synchronous file I/O (`read_text()`) on the async event loop blocks under concurrent load. Use `asyncio.to_thread` or cache at startup. |
| M2 | Backend | `providers/langchain/client.py` | 97-101 | Chat model re-instantiated per request. LangChain objects carry connection pools; recreating them wastes resources. |
| M3 | Backend | `providers/langchain/client.py` | 212-230 | Prompt injection risk. User content is interpolated directly into prompts. Output validation or sandboxing should be considered. |
| M4 | Backend | `providers/tavily/client.py` | 29 | httpx client created and destroyed per request. Prevents TCP connection reuse. |
| M5 | Backend | `providers/extraction/client.py` | 25, 61 | Same httpx-per-request issue in both extraction providers. |
| M6 | Backend | `providers/extraction/client.py` | 137-140 | Fallback decision based on string matching in error messages. Brittle; should use structured error classification. |
| M7 | Backend | `services/orchestration.py` | 250-344 | Stale artifact references in the legacy processing path. Local variable goes stale between `_ensure_run_active` checks. |
| M8 | Backend | `services/orchestration.py` | 975-980 | `_ensure_run_active` reads full artifact from DB just to check `status`. Called many times per run. A lightweight cancellation check would be far more efficient. |
| M9 | Backend | `services/orchestration.py` | 419 | Inline text forced to `ContentFormat.MARKDOWN`. Plain text with `#`, `*`, `` ` `` characters will be mis-parsed. |
| M10 | Backend | `services/orchestration.py` | 1416 | Full `raw_output` serialized into downstream agent prompts, inflating token counts unnecessarily. |
| M11 | Backend | `services/worker.py` | 48-85 | Worker processes jobs sequentially. Queued runs execute one at a time. |
| M12 | Backend | `services/worker.py` | 71-80 | `ProviderError` treated as non-retriable at worker level, even when the error's own `retriable` flag is set. |
| M13 | Backend | `api/main.py` | 281-296 | Manual JSON parsing instead of FastAPI body declaration. Bypasses validation formatting and OpenAPI generation. |
| M14 | Backend | `domain/models.py` | 352 | `overall_score` has no `Field(ge=0, le=100)` constraint. Imported artifacts could carry out-of-range scores. |
| M15 | Backend | `config.py` | 93 | `lru_cache` on `get_settings()` prevents override in tests. No `cache_clear()` in test setup. |
| M16 | Backend | `api/dependencies.py` | 106 | Runtime mode compared via `.value == "live"` instead of `is RuntimeMode.LIVE`. Inconsistent with the rest of the codebase. |
| M17 | Frontend | `ReviewWorkbench.tsx` | 56 | `API_BASE_URL` duplicated between ReviewWorkbench.tsx and api.ts. Divergence would silently break SSE. |
| M18 | Frontend | `ReviewWorkbench.tsx` | 215-236 | EventSource handler captures stale closure. `refreshArtifactCoalesced` is not `useCallback`-wrapped. |
| M19 | Frontend | `ReviewWorkbench.tsx` | 774-779 | Weak sessionStorage type guards. Only check one key; malformed payloads pass through. |
| M20 | Frontend | `ReviewWorkbench.tsx` | 184 | Full artifact serialized to sessionStorage on every state change. Can exceed the ~5MB quota for large documents. |
| M21 | Frontend | `DocumentPane.tsx` | 578 | Resize handler fires without debounce. `getBoundingClientRect` runs for every anchor-comment pair per frame. |
| M22 | Frontend | `DocumentPane.tsx` | 580 | Connector paths go stale. `anchorRefs`/`commentRefs` are stable ref objects; the effect doesn't re-fire when entries mount/unmount. |
| M23 | Frontend | `RunMetrics.tsx` | 13, 17 | Shows "0%" when no data exists. Implies a score of zero rather than "not yet computed." |
| M24 | Frontend | `api.ts` | -- | No `AbortController` support. Stale responses from cancelled navigations can overwrite current state. |

### Low

| # | Area | Summary |
|---|------|---------|
| L1 | Backend | `ValidationError` name shadows `pydantic.ValidationError`. |
| L2 | Backend | `AgentFinding.confidence` has no `[0, 1]` range constraint. |
| L3 | Backend | No upper-bound validation on numeric settings (temperature, max bytes, poll interval). |
| L4 | Backend | `_progress_for_artifact` treats `running` count as boolean (`0.5 if running`). |
| L5 | Backend | `_todo_sort_key` assumes non-empty `anchor.segments`; will `IndexError` on empty. |
| L6 | Backend | Broad `except Exception` in LangChain provider masks programming errors as `ProviderError`. |
| L7 | Backend | Tavily retry retries non-retriable 4xx errors (400, 401, 403). |
| L8 | Backend | Fake Tavily key in OpenAI wrapper could confuse maintainers. |
| L9 | Backend | Route handlers return `object` instead of response models; defeats OpenAPI schema generation. |
| L10 | Backend | `SENTENCE_PATTERN` regex doesn't handle abbreviations (`Dr.`, `U.S.`, `e.g.`). |
| L11 | Backend | No tests for `PostgresRunRepository`. SQL and dual-write issues are untested. |
| L12 | Backend | No direct tests for `TrafilaturaExtractionProvider` or `TavilyExtractionProvider`. |
| L13 | Frontend | `typeof window === "undefined"` guards are dead code in `"use client"` component. |
| L14 | Frontend | `SelectionDraft` interface duplicated in three files. Should be in `types.ts`. |
| L15 | Frontend | `window.confirm` blocks main thread. Custom dialog would be more accessible. |
| L16 | Frontend | Redundant comment sorting (once in ReviewWorkbench, again in DocumentPane). |
| L17 | Frontend | `ThreadCards` has a 14-prop surface; indicates need for context or reducer. |
| L18 | Frontend | Delete comment button lacks confirmation dialog. |
| L19 | Frontend | Reply/edit textareas lack `aria-label`. |
| L20 | Frontend | Text selection is mouse-only. Keyboard users cannot create comments. |
| L21 | Frontend | Select elements in `ReviewToolbar` lack accessible labels. |
| L22 | Frontend | Export buttons not disabled when no artifact exists. |
| L23 | Frontend | `as` casts on select values are unsafe; no runtime check. |
| L24 | Frontend | `createRunFromFile` in api.ts is dead code. |
| L25 | Frontend | 18+ `useState` hooks in ReviewWorkbench; reducer would improve predictability. |
| L26 | Infra | API Dockerfile does not copy `uv.lock`; builds are non-reproducible. |
| L27 | Infra | Both Dockerfiles run containers as root. |
| L28 | Infra | `.agents/` is untracked but not in `.gitignore`. |

---

## Architecture Observations

### What's Working Well

- **Domain model design.** Pydantic models are well-typed with comprehensive enum hierarchies. The `ArtifactAnchor` multi-segment model is a good abstraction for representing anchored text spans.
- **Provider abstraction.** Protocol-based interfaces (`AnalysisProvider`, `SimilaritySearchProvider`, `ContentExtractionProvider`) are clean, testable, and make mock/live swapping easy.
- **Agent registry.** Declarative, frozen dataclass registry with dependency expansion and cycle detection. Simple and correct.
- **Frontend component layering.** The `review/` subdirectory contains focused presentational components. The separation between `ReviewWorkbench` (coordinator) and child components is sound in principle.
- **Observability foundation.** Request ID propagation via context vars, structured log fields, and event streaming provide a solid tracing baseline.
- **Documentation.** The `docs/` directory is comprehensive and well-indexed. The `AGENTS.md` progressive-disclosure approach is effective for agent-first development.

### Areas for Improvement

- **ReviewWorkbench is a monolith.** At ~780 lines with 18+ state variables, this component does too much. A `useReducer` or context provider would make state transitions explicit and testable. Related states (editing, selection, reply drafts) should be co-located.
- **Orchestration service is too large.** At ~1,440 lines, `orchestration.py` handles source resolution, normalization, agent execution, anchor resolution, comment creation, summary building, event emission, checkpoint management, and graph construction. Extracting focused services (source resolution, anchor resolution, summary building) would improve testability.
- **Postgres repository is a thin wrapper.** The dual-write inheritance pattern (in-memory + Postgres) creates consistency risks that are hard to test. A dedicated Postgres implementation that doesn't inherit from the in-memory store would be cleaner.
- **No authentication boundary.** The API has no auth, rate limiting, or CSRF protection. Acceptable for local-first, but needs to be addressed before any shared deployment.
- **Test gaps.** Happy paths are well-covered. Error paths, Postgres repository, extraction providers, concurrency, and the SSE stream are untested.

---

## Recommended Priority Order

### Immediate (before any shared deployment)

1. **C4 -- SSRF.** Add URL scheme allowlist and private IP blocking to the extraction provider.
2. **C1 -- SQL injection.** Replace f-string interpolation with `psycopg.sql.Identifier`.
3. **H10 -- Docker secrets.** Add `.env*` to `.dockerignore`.
4. **H6 -- Frontend error handling.** Add try/catch to all six mutation handlers.
5. **H7 -- Error body parsing.** Read and display backend error messages in `parseJson`.

### Short-term (next iteration)

6. **C3 -- Double construction.** Restructure CORS setup to avoid module-level `build_services()`.
7. **C2 -- Comment service.** Add a `list_artifact_ids()` method to the repository protocol, or pass `artifact_id` to comment endpoints so the service doesn't need to scan.
8. **H1 -- Connection pooling.** Introduce `psycopg_pool.AsyncConnectionPool`.
9. **H3 -- SSE timeout.** Add a configurable total timeout to the event stream.
10. **H4 -- Lock cleanup.** Remove artifact locks after run completion.
11. **H9 -- Fix E2E test.** Update the "Comment rail" assertion to match the actual "Run log" heading.

### Medium-term (architecture improvement)

12. **L25/M18 -- ReviewWorkbench refactor.** Extract state into a reducer; stabilize callbacks with `useCallback`.
13. **M2/M4/M5 -- Client reuse.** Create httpx and LangChain clients once and reuse them.
14. **H2 -- Postgres repository.** Rewrite without inheriting from in-memory; add proper transaction handling.
15. **M11 -- Worker concurrency.** Allow bounded concurrent job processing.
16. **L11/L12 -- Test coverage.** Add tests for Postgres repository, extraction providers, and error paths.

---

## Infrastructure Notes

| Item | Status | Note |
|------|--------|------|
| `.env` gitignored | OK | Correctly excluded from version control |
| `.env.example` | OK | No real secrets; good onboarding template |
| Docker reproducibility | Needs fix | API Dockerfile missing `uv.lock` copy |
| Container security | Needs fix | Both images run as root |
| Docker healthchecks | Missing | No `pg_isready` check; cold-start race condition |
| Web image size | Oversized | devDependencies copied to production stage |
| Frontend linting | Missing | No ESLint, Biome, or Prettier configured |
| Agent instructions | Good | Consistent structure, except `similarity.md` lacks excerpt fidelity rules |
| `.agents/` directory | Untracked | Should be added to `.gitignore` |

---

## Test Coverage Summary

| Area | Happy Path | Error Path | Integration | Note |
|------|-----------|------------|-------------|------|
| API routes | Good | Partial | Yes (TestClient) | Missing: SSE timeout, file upload edge cases |
| Domain models | N/A | N/A | N/A | Validated by Pydantic; no custom logic tests needed |
| Agent registry | Good | N/A | N/A | Cycle detection tested |
| Anchor matching | Thorough | Good | N/A | Multi-block, overlap, and ellipsis cases covered |
| Comment service | Good | Partial | N/A | Authorization rules tested; Postgres path broken |
| Export service | Good | N/A | N/A | Markdown and JSON export tested |
| Normalization | Good | N/A | N/A | Block splitting and paragraph chunking tested |
| LangChain provider | Good | N/A | N/A | Structured output parsing tested |
| Tavily provider | Good | N/A | N/A | HTTP error mapping tested |
| Extraction provider | Partial | N/A | N/A | Only fallback tested via stubs |
| Postgres repository | **None** | **None** | **None** | All findings untested |
| Orchestration | Partial | Partial | Yes | LangGraph runtime tested; legacy path less so |
| Frontend components | Good | **None** | N/A | Happy paths tested; no error paths |
| E2E | Partial | Minimal | Yes | One error state; one possibly broken assertion |
