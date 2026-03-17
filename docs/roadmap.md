# Roadmap

Goals, feature ideas, and known improvement areas for the content evaluation platform.
This is a living document — update it when priorities shift or new ideas surface.

Items are grouped by theme, not strict priority order. The DB persistence layer is intentionally
excluded here — that warrants its own planning document when the time comes.

---

## Immediate Priorities

- **Review summary panel above the text under review**
  - Add a new section above the source text pane with:
    - a short content summary
    - a research summary
    - linked similar or overlapping articles
    - the inferred audience
  - De-emphasize audience-agent inline text annotations in the body when they are lower-value than a compact summary view
- **Claim evidence UX**
  - Highlight claims throughout the document and show a nearby supporting source link for each claim
  - Supporting sources may be papers, articles, or other web evidence surfaced by the fact-check flow
  - Prefer evidence presentation that keeps the source text readable instead of overloading the existing comment rail
- **Agent demo review**
  - Review which agents should remain standalone, which should be merged, and which should become summary-only outputs
  - The audience agent currently does not provide enough standalone value to justify its own surface area
  - The current editorial / AI-likelihood / fact-check responsibility split should be reconsidered before adding more agent complexity
- **Value/fact-check/similarity restructuring**
  - Make value analysis depend on fact-check output
  - Fully replace the standalone similarity agent with fact-check-driven overlap and source research
  - Revisit whether editorial suggestions should explicitly consume fact-check and AI-likelihood outputs rather than duplicating them independently
- **Token cost accuracy**
  - Replace hardcoded or incomplete cost estimation with pricing sourced from the official OpenAI pricing documentation
  - Keep the implementation robust to future pricing changes and unknown model names

## Observability & Cost Visibility

- ~~**Token usage and cost display**~~ ✅ *done — `docs/plans/completed/2026-03-16-token-usage-cost-display.md`*
- ~~**RunMetrics "not yet computed" state**~~ ✅ *done — shows "—" when score is absent*
- **Official pricing-backed cost estimates**
  - Move cost estimation away from repo-local assumptions and source it from the official OpenAI pricing docs
  - Keep unknown-model behavior conservative (`—` rather than incorrect pricing)

---

## Agent Quality

- **Agent architecture rethink**
  - Rework the agent graph around the actual user value of each agent rather than preserving the current one-agent-per-concern shape
  - Decide which outputs belong:
    - in the document body
    - in the new summary section above the text
    - in editorial suggestions
    - in the run log only
- **Similarity agent LLM upgrade**
  - Replace the standalone similarity agent path with fact-check-driven research and overlap reporting
  - Any remaining similar-content surfacing should hang off the fact-check/evidence system rather than a separate top-level agent
- **Fact-check tuning**
  - The deep researcher graph is vendored and working, but prompt quality and claim extraction
    could be refined based on real article results
  - Consider adjusting how many claims are extracted and how the redundancy finding is framed
  - Expand fact-check output so it can power:
    - the review summary panel
    - claim-by-claim evidence links in the document
    - downstream value/editorial reasoning
- **New specialist agents**
  - SEO analysis: headline quality, keyword density, meta description suggestions
  - Readability: Flesch-Kincaid or similar, sentence complexity, passive voice density
  - Tone consistency: flags when the article shifts register unexpectedly
  - Source quality: assesses whether cited or linked sources are credible
- **Agent dependency graph**
  - Editorial suggestions may need to consume fact-check and AI-likelihood output explicitly
  - Value analysis should depend on fact-check output
  - Audience may be better represented as a summary-field output than a full annotation-heavy standalone agent

---

## Review Workbench UX

- **Research summary region**
  - Add a new section above the text pane for summary, research summary, audience, and similar-article links
- ~~**Fix stale connector paths** *(M22 from code review)*~~ ✅ *done — connector recomputation now reacts to document/layout changes instead of only stable ref objects*
- ~~**Debounce resize handler** *(M21)*~~ ✅ *done — connector recomputation is frame-scheduled and resize-throttled*
- ~~**AbortController for stale responses** *(M24)*~~ ✅ *done*
- ~~**sessionStorage size cap** *(M20)*~~ ✅ *done — browser storage now keeps restore metadata and refetches canonical artifacts by run ID*
- ~~**Todo export**~~ ✅ *done — compact Markdown todo export is available from the toolbar and `/api/v1/runs/{run_id}/export.todo.md`*
- **Inline claim evidence**
  - Highlight claims in the document and render a nearby supporting link or evidence affordance
  - Keep the UI readable when multiple claims or evidence links appear in one paragraph
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
- ~~**Retryable error propagation** *(M12)*~~ ✅ *done — worker retry policy now honors `ProviderError.retriable`*
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
