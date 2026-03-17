# Roadmap

Goals, feature ideas, and known improvement areas for the content evaluation platform.
This is a living document — update it when priorities shift or new ideas surface.

Items are grouped by theme, not strict priority order. The DB persistence layer is intentionally
excluded here — that warrants its own planning document when the time comes.

---

## Observability & Cost Visibility

- ~~**Token usage and cost display**~~ ✅ *done — `docs/plans/completed/2026-03-16-token-usage-cost-display.md`*
- ~~**RunMetrics "not yet computed" state**~~ ✅ *done — shows "—" when score is absent*

---

## Agent Quality

- **Similarity agent LLM upgrade**
  - Currently deterministic: Tavily search → code-side synthesis, no LLM involved
  - Planned: full LLM-backed chain (search-plan → retrieve → rank → summarize)
  - The `similarity.md` instruction file already exists and loads; the execution path just bypasses it
- **Fact-check tuning**
  - The deep researcher graph is vendored and working, but prompt quality and claim extraction
    could be refined based on real article results
  - Consider adjusting how many claims are extracted and how the redundancy finding is framed
- **New specialist agents**
  - SEO analysis: headline quality, keyword density, meta description suggestions
  - Readability: Flesch-Kincaid or similar, sentence complexity, passive voice density
  - Tone consistency: flags when the article shifts register unexpectedly
  - Source quality: assesses whether cited or linked sources are credible
- **Agent dependency graph**
  - Some agents could benefit from reading the fact-check result (e.g. editorial agent could
    flag factual issues surfaced by fact-check in its rewrite suggestions)

---

## Review Workbench UX

- **Fix stale connector paths** *(M22 from code review)*
  - SVG connector lines go stale when anchor/comment refs mount or unmount
- **Debounce resize handler** *(M21)*
  - Connector path recalculation fires on every pixel of resize
- ~~**AbortController for stale responses** *(M24)*~~ ✅ *done*
- **sessionStorage size cap** *(M20)*
  - Full artifact is serialized to sessionStorage on every state change — can hit ~5MB quota on large documents
  - Replace with run-ID-only storage and on-demand fetch
- **Todo export**
  - Export accepted agent suggestions as a compact Markdown checklist, ordered by source position
  - Already specced in `docs/frontend/annotation-review-workbench.md` and `docs/backend/analysis-pipeline.md`
- **Keyboard navigation**
  - Move between findings with arrow keys or `j`/`k`
  - Accept/reject the focused finding with a hotkey
- **Filtering and sorting in the comment rail**
  - Filter by agent, category, review state (accepted/rejected/pending)
  - Sort by position in document vs. by confidence

---

## Backend Quality

- **Prompt injection protection** *(M3)*
  - User article content is interpolated directly into LLM prompts
  - Should be sanitized or isolated via structured message roles
- **Async instruction loading** *(M1)*
  - `load_instruction_text()` uses synchronous `read_text()` on the async event loop
- **Retryable error propagation** *(M12)*
  - `ProviderError.retriable` flag is set but ignored at the worker level
- **FastAPI body declaration** *(M13)*
  - `create_run` manually parses JSON instead of using a FastAPI body model
- **Stop inflating downstream prompts** *(M10)*
  - Full `raw_output` from upstream agents is serialized into downstream agent prompts
  - Should pass only the structured summary/findings, not the entire raw payload
- **overall_score bounds validation** *(M14)*
  - No `ge=0/le=100` constraint on the field; invalid scores could silently pass through

---

## Infrastructure & Security

- **Authentication layer**
  - No auth, rate limiting, or CSRF protection — intentional for local-first use
  - Required before any shared or multi-user deployment
- ~~**API URL deduplication** *(M17)*~~ ✅ *done — `API_BASE_URL` exported from `api.ts` and imported everywhere*
- **Non-root Docker containers** *(L27)*
  - Both Dockerfiles run as root
- **Reproducible API Docker builds** *(L26)*
  - `uv.lock` is not copied into the API Dockerfile
- **Frontend error path tests** *(H8)*
  - No tests cover frontend error or failure paths

---

## Longer-Term Goals

- **Multi-reviewer support** — multiple people can annotate the same artifact and see each other's review states
- **Batch runs** — submit a set of articles and get a ranked output report
- **Feedback loop** — reviewer decisions feed back into agent instruction tuning over time
- **Custom agent configuration** — let users configure which agents run and at what model/cost tier without code changes
- **Artifact versioning** — track edits to the article and re-run affected agents without a full re-analysis
