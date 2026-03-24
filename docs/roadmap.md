# Roadmap

Goals, feature ideas, and known improvement areas for the content evaluation platform.
This is a living document — update it when priorities shift or new ideas surface.

Items are grouped by theme, not strict priority order. The DB persistence layer is intentionally
excluded here — that warrants its own planning document when the time comes.

---

## Immediate Priorities

- **Agent overhaul**
  - Rewrite the specialist prompts around actual editorial value rather than bare schema compliance
  - Define clearer roles for:
    - AI-likelihood as a concrete AI-writing-pattern detector with actionable fixes
    - editorial as a structure-and-conversion reviewer rather than a generic rewrite suggester
    - synthesis as a decision-maker with an explicit rubric
    - value and audience as evidence-backed judgment calls rather than vague summaries
  - Revisit the shared analysis-provider prompt so agent identity, upstream context, and task framing are more legible to the model
  - Tighten agent outputs around "fewer, sharper findings" instead of broad low-value coverage
- **Fact-check prompt and contract tuning**
  - Keep the deep research flow, but narrow the prompt and output contract so claim verification, overlap research, and citation gaps are more consistent
  - Improve how fact-check results feed downstream value, editorial, and synthesis reasoning
- **Prompt injection protection** *(M3)*
  - User article content is interpolated directly into LLM prompts
  - Should be sanitized or isolated via structured message roles
- **Stop inflating downstream prompts** *(M10)*
  - Full `raw_output` from upstream agents is serialized into downstream agent prompts
  - Should pass only the structured summary/findings, not the entire raw payload

---

## Agent Quality

- **New specialist agents**
  - SEO analysis: headline quality, keyword density, meta description suggestions
  - Readability: Flesch-Kincaid or similar, sentence complexity, passive voice density
  - Tone consistency: flags when the article shifts register unexpectedly
  - Source quality: assesses whether cited or linked sources are credible

---

## Review Workbench UX

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

- **Async instruction loading** *(M1)*
  - `load_instruction_text()` uses synchronous `read_text()` on the async event loop
- **FastAPI body declaration** *(M13)*
  - `create_run` manually parses JSON instead of using a FastAPI body model
- **overall_score bounds validation** *(M14)*
  - No `ge=0/le=100` constraint on the field; invalid scores could silently pass through

---

## Infrastructure & Security

- **Authentication layer**
  - No auth, rate limiting, or CSRF protection — intentional for local-first use
  - Required before any shared or multi-user deployment
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

## Artifact Structure Direction

- **Near-term revision provenance**
  - Keep one main mutable artifact as the live workbench object
  - When a revision is applied, archive the immediately previous draft as a snapshot inside the artifact
  - Preserve only fact-check and targeted research against that previous-draft snapshot
  - Continue clearing or recomputing the cheaper draft-shape-dependent analysis surfaces on the new draft
- **Possible future pivot: immutable run and research artifacts**
  - If the product grows into deeper revision history, branch comparisons, or reusable research libraries, pivot toward separate immutable artifacts for:
    - each full analysis run
    - each targeted research run
  - The review workbench would then compose multiple artifacts into one session view rather than mutating a single artifact in place
  - This is intentionally deferred for now because it adds substantial storage, merge, and UI complexity
