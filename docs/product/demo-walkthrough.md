# Demo Walkthrough

**Pinned commit:** `eb98596` (`fix(review): lock workbench during revision`).

The demo is a time capsule of the product at the pinned commit. It is intentionally allowed to drift from the live product between fixture captures — reviewers should read this doc as "how the product looked and behaved at commit `eb98596`." Update this line whenever the fixtures are re-captured.

## Purpose

Showcase the full content-evaluation workflow to demo visitors without calling the backend or any LLM. The demo is **somewhat static**: intake, running, and post-apply phases are presentational, while the review workbench and diff review phases hydrate the real components from captured fixtures so visitors can actually click, comment, and accept or reject changes.

A persistent explanatory card sits above the workbench at each phase and explains what the phase represents, which agents or actions are involved, and what the visitor should do to continue.

## Demo Mode Assumptions

- Demo state is driven entirely from fixtures committed to the repo. No requests to `/api/*` are made while the visitor interacts with the demo.
- The demo is pinned to a specific commit (see top of this doc). Drift between the pinned demo and the live product is accepted; the demo is re-captured when the drift becomes meaningful enough to justify the work.
- Phase 3 (review workbench) and Phase 4 (diff review) reuse the real React components, hydrated from captured artifact fixtures. Phases 1, 2, and 5 are presentational.
- The demo narrative is additive: the top-card copy is part of demo mode only and does not render in the real workbench.

### Interactivity Budget

Real interactivity is expensive to fake well, so we only spend it where it teaches a visitor something about the product:

- **Live in the demo.** Accept / reject / uncertain on agent comments, replying to comments, adding a standalone comment on a selection, switching diff-review modes, and applying or discarding diffs. All of these operate against local in-memory artifact state and never reach a backend.
- **Presentational in the demo.** Source-type switching in intake, URL/file/artifact import flows, running-view SSE events, token-usage recomputation, research follow-up submission, and any other control whose authentic behavior would require the backend.
- **Controls that would submit to the backend are either locked or downgraded to a no-op** with a short inline hint. Visible-but-dead controls are avoided.

## Phase Inventory

Phases are documented incrementally. Only the phases that have been walked through are filled in below.

### Phase 1 — Intake

The visitor lands on the main workbench page with the demo article already pasted and previewed. They see the full intake surface, the Preview button is already active, and the parsed article is rendered below the composer as `Text under review`.

**Current UI (what the visitor sees).**

- Top bar reads `Content Evaluation` above a level-1 `Analysis workbench` heading.
- `Choose content` dropdown with four source types, preset to `Pasted text`:
  - Pasted text
  - URL
  - Text file
  - Import artifact
- Three agent checkboxes, all checked by default:
  - Human Voice
  - Structure and Conversion Review
  - Fact Check
- Pasted-text textarea prepopulated with the demo article (`demo-content/before-you-publish-an-ai-assisted-post.md`).
- Action row with `Analyze content` (primary) and `Preview` (active). A `Preview ready` status label sits beside the buttons because the parsed preview has already loaded.
- `Text under review` panel renders the parsed article with its heading hierarchy, paragraphs, and inline markdown so the visitor can see what the pipeline would receive.

**Captured fixtures.**

- `demo-content/before-you-publish-an-ai-assisted-post.md` — source article, pasted into the textarea on load.
- `demo-content/fixtures/phase-1-preview.json` — `/api/v1/sources/preview` response for the article at the pinned commit. Hydrates the `Text under review` panel without a backend call.

**What the demo needs to fake.**

- Skip the `Preview` round-trip entirely. The parsed document comes from `phase-1-preview.json`, so the `Text under review` panel is populated on first paint, not after a click.
- The `Choose content` dropdown is **locked to `Pasted text`**. The other three source types remain visible in the list so visitors see they exist, but the dropdown cannot be switched. The top-card copy carries the "four intake paths" message verbally instead of walking each one through.
- Agent checkboxes are visible and checked but not interactive — toggling them has no effect on the staged run.
- `Analyze content` is the one live control. It advances the demo to Phase 2 and starts the canned Phase 2 animation; it does not call `/api/runs`.
- `Preview` is already in its `Preview ready` state on load and does not need to be re-clickable.

**Top-card narrative copy.**

> **Step 1 of 5 — Intake**
>
> The user can choose between four different ways of uploading content: **file upload**, **pasted text**, **JSON artifact import**, and **URL retrieval**. Each source type parses the draft into the same normalized structure before analysis begins. The content for this demo is prepopulated with a short essay about reviewing AI-assisted posts, and the Preview step has already been done for you — no API calls to LLMs are made during this walkthrough.
>
> Press **Analyze content** to kick off the analysis run.

**Notes for later phases.**

- Phase 2 will be a timed animation, not a replayed SSE stream. A short script advances the progress bar and per-agent status transitions; no real event feed is needed.
- Phase 3 will hydrate the full `ReviewWorkbench` from a captured terminal artifact fixture and should read as a normal review session. Accept / reject / reply / add-comment mutate local state only.
- Phase 4 has two variants — surgical (`Apply changes`) and rewrite (`Rewrite draft`) — each backed by its own captured diff-review fixture. Apply and discard mutate local state only.
- Phase 5 (post-apply) is presentational: it loads a post-apply artifact fixture that preserves the original-draft findings alongside the applied revision.

### Phase 2 — Running

After the visitor clicks `Analyze content`, the intake shell is replaced by a focused running view. The full review workbench does not render behind it — Phase 2 is intentionally a separate shell. The visitor watches progress advance, per-agent status cards transition, and a live preview card rotates through partial findings that arrive as agents complete.

Reference captures from a real run at the pinned commit live in `demo-content/reference/phase-2-*.png`.

**Current UI (what the visitor sees).**

- Top bar keeps `Content Evaluation` and the `Analysis workbench` heading.
- `RUN PROGRESS` header above a progress bar that animates even when the percent value is stable.
  - A `N% COMPLETE` label on the left and a `RUNNING` status on the right with three animated dots.
  - Progress is coarse: it jumps as agents complete (roughly 17% on start, ~50% after Human Voice completes, then waits while Fact Check gathers research). The progress bar keeps animating during these plateaus so the visitor can see work is still in flight.
- `PARTIAL FINDINGS` card below the progress bar with a `LIVE PREVIEW` label top-right.
  - Before any agent completes: shows `Waiting for the first agent result.`
  - Once findings arrive: rotates through them on a 5-second cadence. The card shows the agent identifier (`AI_LIKELIHOOD` etc.) top-left, a `FINDING N OF M` counter top-right, and the rationale plus suggested rewrite body.
  - Card height is fixed; long findings scroll inside the card so the surrounding layout does not shift.
- Per-agent status grid with one card per selected agent, in the order `Human Voice`, `Fact Check`, `Structure and Conversion Review`. Each card shows:
  - Agent display name
  - Status pill (`PENDING` / `RUNNING` / `COMPLETED`)
  - A short status line (`Agent running`, `Agent completed`, or the raw agent id like `editorial` / `fact_check` when still pending)
- Collapsible `TOKEN USAGE` disclosure below the status grid.
  - Empty until at least one agent completes, then populates incrementally.
  - Expanded, it shows a small table: Agent, Model, In, Out, Est. cost, with a `Total` row at the bottom.
- Collapsible `RUN LOG (N events)` disclosure.
  - The count in the label advances as events arrive.
  - Each row renders one event: a type prefix (`run`, `extraction`, `normalization`, `Human Voice`, `Fact Check`, etc.), a short human-readable message, and a right-side metadata stack (status pill, agent id / `run`, model / `not recorded` / `inline-input`).
- Collapsible submitted-content preview at the bottom, controlled by a `Hide submitted content` / `Show submitted content` button. Renders the parsed article via the non-interactive `DocumentPane` so the visitor can reread the draft while waiting.
- `Stop run` button fixed in the bottom-right of the viewport.

**Observed timings at pinned commit (real run against the demo article).**

| Moment | State |
| ------ | ----- |
| `t=0s` (click) | `0% COMPLETE`, agents transition from `QUEUED` to `RUNNING` shortly after |
| `t≈1s` | `17% COMPLETE`, Human Voice `RUNNING`, others `PENDING`, `Waiting for the first agent result.` in the preview card |
| `t≈15s` | Human Voice `COMPLETED`, Fact Check `RUNNING`, `50% COMPLETE`, preview card cycling through Human Voice findings (`FINDING 4 OF 5` etc.) |
| `t≈30s–2m` | Long Fact Check research phase; progress bar holds at `50%` while the run log grows with `Fact Check is gathering intermediate context` events and the preview card keeps rotating |
| `t≈2m30s` | Fact Check `COMPLETED`, `Structure and Conversion Review` transitions `RUNNING → COMPLETED` very quickly, and the Phase 2 shell is replaced by the Phase 3 review workbench almost immediately after |

Human Voice consistently finishes first in real runs; Fact Check dominates the runtime because of live web research. `Structure and Conversion Review` is fast and typically flips to `COMPLETED` only moments before the shell transitions to Phase 3, so its completed state is barely visible on the per-agent status card.

**Captured fixtures.**

_None yet._ Phase 2 is a scripted animation, not a replayed event stream. The animation is built from this doc plus data the visitor will see for real once Phase 3 is wired (the partial-findings card can pull its rotated content from the Phase 3 `agent_results` array, so no separate Phase 2 event fixture is needed).

Reference screenshots from the real run at the pinned commit:

- `demo-content/reference/phase-2-t0-launch.png` — 17% complete, Human Voice running, `Waiting for the first agent result.`
- `demo-content/reference/phase-2-t15-human-voice.png` — 50%, Human Voice done, Fact Check running, preview rotating through Human Voice findings
- `demo-content/reference/phase-2-t35-mid-run.png` — token usage + run log expanded so the internal structure is visible
- `demo-content/reference/phase-2-t65-fact-check-running.png` — long Fact Check plateau, preview card still rotating
- `demo-content/reference/phase-2-t110-later.png` — late-stage plateau before transition to Phase 3

**What the demo needs to fake.**

- A scripted progress sequence. Suggested beats: `0% → 17% → 50% → 85% → 100%` on a generous total duration (roughly 15–20 seconds) that keeps the visitor engaged without forcing the real 2–3 minute wait.
- A matching status-transition script for each agent card: `queued → running → completed`, staggered across the progress beats. `Structure and Conversion Review` should flip to `COMPLETED` just before the Phase 3 transition fires, mirroring the real pipeline where its completion is what closes out the run.
- A rotating findings preview on the real 5-second cadence, drawing from a small curated set of Human Voice findings sourced from the Phase 3 artifact fixture.
- A run log that appends entries as each scripted event fires. Token usage populates incrementally alongside.
- Disclosures start collapsed, matching the real default, and remain interactive so a curious visitor can expand them.
- `Stop run` button is visible but non-functional. Clicking it shows a brief "Demo run cannot be canceled" hint or is downgraded to a no-op.
- The submitted-content preview toggle is live (local-only state) because it is pure client behavior.

**Top-card narrative copy.**

> **Step 2 of 5 — Running**
>
> Three agents analyze the draft in parallel: **Human Voice** estimates how much of the piece reads like AI-generated text, **Structure and Conversion Review** inspects the editorial flow, and **Fact Check** verifies claims by running live web research.
>
> Human Voice tends to finish first — its findings rotate through the live preview above while the slower agents are still working. In the real product this runs against live LLMs and takes a few minutes. This demo replays a recorded run on a compressed timeline and moves to the review workbench automatically when it finishes.


### Phase 3 — Review workbench

This is the product's core. The Phase 2 shell is replaced by the full `ReviewWorkbench`, and the visitor lands on a workbench that is already **partially reviewed**: eight agent suggestions are accepted, two are rejected, three are marked uncertain, and one reviewer-authored standalone comment exists on the source text. This gives the visitor something to read rather than a cold wall of unreviewed comments, and it is also what enables the revision actions (`Apply changes` / `Rewrite draft`) to be visible immediately.

Reference captures of the real review workbench at the pinned commit live in `demo-content/reference/phase-3-*.png`.

**Current UI (what the visitor sees).**

- Top toolbar
  - `Human Voice` and `Structure and Conversion Review` render as re-runnable agent chips. `Fact Check` carries an `ALREADY RUN` badge because it cannot be cheaply re-run.
  - Action row: `New analysis`, `Add selected analysis`, `Export Todo`, `Export Markdown`, `Export JSON`, and a `RUN COMPLETED` status label.
- `Choose how to revise the current draft` CTA row with `Apply changes` and `Rewrite draft` buttons. The CTA repeats at the top and bottom of the workspace (`revision-cta-top` and `revision-cta-bottom`) so reviewers do not have to scroll back up after finishing the comments. The CTA is rendered only because at least one agent suggestion has been accepted.
- `Analysis overview` section with:
  - `Overall score` tile (`62%` against the demo article) paired with an inline breakdown paragraph (`Baseline 72. Human Voice: 93% AI likelihood (strong drag). Fact Check: 5 overlapping articles (16% originality).`).
  - `TL;DR` paragraph summarizing the article.
  - Four cards — `Article profile` (word count, reading time, format pills, structural completeness), `Overlap research` (`Originality signal 16%` plus a ranked list of overlapping articles with notes), `Human voice` (voice signal `7%`, verdict copy, "5 AI-pattern signals flagged as inline comments below"), `Audience`.
  - Optional `Research summary` paragraph below the grid when the research narrative is present and not a duplicate of the TL;DR.
- `Research` panel — compact prompt composer with the Fact-Check-suggested prompt preloaded, a `Loaded from fact-check metadata when available.` hint, and a `Research` submit button.
- Collapsible `Token usage` disclosure.
- Review-progress badge (`3 OF 13 COMMENTS REVIEWED` at the demo's seeded state).
- `Text under review` document pane with inline highlights for every agent anchor and a paragraph-scoped comment rail to the right. For each comment the rail renders:
  - Agent label (`HUMAN VOICE AGENT`, `STRUCTURE AND CONVERSION REVIEW AGENT`, `FACT CHECK AGENT`) plus a review-state pill (`UNREVIEWED`, `ACCEPTED`, `REJECTED`, or `UNCERTAIN`).
  - Commentary body.
  - For Fact Check: a structured `Claim / Verdict: SUPPORTED|MIXED|REFUTED / evidence / Sources` block with hostname-only links.
  - A boxed `Suggestion:` call-to-action.
  - Action row: `Accept` / `Reject` / `Uncertain` / `Add comment`.
- Reviewer standalone comment: the seeded demo has one on the penultimate paragraph anchored to `"AI detectors can help with that review because they are now fairly reliable signals"`, authored as `Workspace reviewer`, softening the detector claim. It renders with `Edit` / `Delete` affordances instead of review-state pills.

**Captured fixtures.**

Phase 3 ships three snapshots of the same artifact. Each snapshot has the runtime artifact JSON plus the three export files (`export.md`, `export.json`, `export.todo.md`) captured at the same state.

| Snapshot | Agent-comment states | Purpose |
| -------- | -------------------- | ------- |
| `pristine` | 13 unreviewed, 0 human comments | Illustrative "nothing touched yet" state. Useful for screenshots and as a reset target. |
| `reviewed` | 8 accepted, 3 uncertain, 2 rejected, plus 1 reviewer comment | **Hydrate the demo's Phase 3 from this fixture.** Seeds a realistic mid-review session: mixture of review states across all three agents, one reviewer standalone comment, revision CTAs already unlocked. |
| `all-accepted` | 13 accepted, plus the 1 reviewer comment | **Input for the Phase 4 capture.** When the visitor clicks `Apply changes`, the demo bridges from the reviewed state by auto-accepting any remaining unreviewed-or-rejected-or-uncertain agent comments, then loads the Phase 4 diff-review fixture that was generated off this snapshot. |

Files in `demo-content/fixtures/`:

- `phase-3-artifact-pristine.json`, `phase-3-export-pristine.md`, `phase-3-export-pristine.todo.md`
- `phase-3-artifact-reviewed.json`, `phase-3-export-reviewed.md`, `phase-3-export-reviewed.todo.md`
- `phase-3-artifact-all-accepted.json`, `phase-3-export-all-accepted.md`, `phase-3-export-all-accepted.todo.md`

No separate `export.json` fixture is kept: `GET /api/v1/runs/{id}/export.json` is byte-identical to `GET /api/v1/runs/{id}`, so the demo's `Export JSON` button can simply serialize the in-memory artifact instead of serving a captured file. Verified during capture by diffing both responses at the reviewed state.

The `reviewed` snapshot also contains one reviewer standalone comment on the `"AI detectors can help with that review because they are now fairly reliable signals"` span, softening the detector claim.

**Export buttons in demo mode.**

The `Export Todo`, `Export Markdown`, and `Export JSON` buttons in the toolbar should work in the demo, without any backend call:

- `Export JSON` serializes the in-memory artifact to a downloadable JSON blob. The backend endpoint and the runtime-artifact endpoint return byte-identical payloads, so client-side serialization is lossless and stays live as the visitor accepts or rejects more comments.
- `Export Markdown` serves the captured `phase-3-export-{state}.md` fixture that matches the hydrating artifact. The markdown export uses a server-side renderer we do not mirror client-side, so the demo accepts the fidelity loss: the file reflects the state at capture time, not the visitor's latest interactions. Fine for the demo.
- `Export Todo` serves the captured `phase-3-export-{state}.todo.md` fixture. Since the todo file only lists *accepted* suggestions, it is the export most sensitive to the visitor's interactions — but the same argument applies.

"Matches the hydrating artifact" means: when the demo loads from `phase-3-artifact-reviewed.json`, the export buttons serve `phase-3-export-reviewed.{md,todo.md}`. If we later add a "reset" affordance that switches back to `phase-3-artifact-pristine.json`, the export buttons switch in lock-step.

**What the demo needs to fake.**

- Hydrate the workbench from `phase-3-artifact-reviewed.json` on Phase 3 entry. Accept / reject / uncertain / reply / delete / add-comment mutations are re-implemented as pure reducer actions against the in-memory artifact — the existing `workbench-state.ts` reducer already supports this, the demo just needs to skip the network calls in the action handlers.
- Wire the three export buttons to the local fixtures per above.
- Disable `Research` submission: the button is visible but clicking it is a no-op with an inline "Research is disabled in the demo" hint in the research panel's local-error slot.
- Disable `New analysis` and `Add selected analysis` (agent follow-up) — they are part of the intake surface, not the review experience. Same no-op treatment.
- Keep `Apply changes` and `Rewrite draft` live; they advance to Phase 4. See Phase 4 notes for how those transitions hydrate from captured diff fixtures.

**Top-card narrative copy.**

> **Step 3 of 5 — Review workbench**
>
> Every agent comment lives next to the source text it is commenting on. Agent findings offer a suggestion you can **accept**, **reject**, or mark **uncertain**, and you can reply to any comment to add reviewer context or override the agent's take. You can also select any text to add a standalone reviewer comment of your own.
>
> This walkthrough opens mid-review: eight suggestions are accepted, three marked uncertain, two rejected, and one reviewer-authored comment sits on the closing paragraph. The revision actions below are unlocked. Try toggling a few decisions yourself — when you are ready, pick **Apply changes** (surgical edits, only accepted suggestions are promoted) or **Rewrite draft** (full-document rewrite with an optional direction prompt) to move on to the diff review.

### Phase 4 — Diff review

After the visitor picks a revision path from Phase 3, the workbench hands off to a dedicated diff-review surface that compares the current draft against a candidate revision produced by the analysis provider. Two paths feed in: `Apply changes` (surgical, per-comment edits) and `Rewrite draft` (full-document rewrite conditioned on a short direction prompt). Both land on the same `RevisedMarkdownPanel`, but with different review defaults.

Reference captures at the pinned commit live in `demo-content/reference/phase-4-*.png`.

**Current UI (what the visitor sees).**

- Top toolbar collapses: only a back-style affordance back to the workbench, the draft title, and a status label remain. The full agent chip row and export actions are suppressed while the diff panel is in flight so the visitor focuses on the proposed revision.
- `RevisedMarkdownPanel` renders the diff review and is the only live surface in the phase.
  - `Original-draft findings` are not rendered here — they only re-appear post-apply in Phase 5.
  - Header strip shows the revision mode (`Surgical revision` or `Full rewrite`), the direction prompt (rewrite only), and a `Discard revision` affordance that returns the visitor to Phase 3 without applying.
  - View toggle: `Inline` vs `Side-by-side`. Surgical mode defaults to inline; rewrite mode defaults to side-by-side. Toggling is local and does not reshape the underlying diff data.
  - Inline view: each diff item renders as a tight block with `before` (strikethrough) and `after` (addition) hunks plus per-diff decision controls (`Accept`, `Reject`, leave pending). The primary action is `Apply full revision`, enabled once **at least one** diff is accepted.
  - Side-by-side view: the original and the candidate render as two full-width columns, color-coded by change type, with no per-diff controls. The primary action is `Apply full revision`, which promotes the entire candidate in one go.
- `Apply full revision` applies the current diff state to the draft and advances to Phase 5. `Discard revision` drops the candidate and returns to Phase 3 (the accepted/rejected/uncertain states on the original comments are preserved).

**Paths into Phase 4.**

| Entry | Mode | Default view | Decision model |
| ----- | ---- | ------------ | -------------- |
| `Apply changes` | `surgical` | `inline` | Each diff is an accept/reject/pending call; apply promotes only the accepted hunks. Rejected and pending diffs keep the original lines. |
| `Rewrite draft` | `rewrite` | `side-by-side` | The candidate is the rewritten draft as a whole. If the visitor makes no per-diff decisions (the default in side-by-side), applying promotes the full candidate. If they switch to inline and make per-diff decisions, those decisions are honored on apply. |

**Captured fixtures.**

Phase 4 ships one rewrite snapshot. The surgical snapshot is captured implicitly as the starting state of Phase 5 — capturing a pre-apply surgical variant for parity is tracked under "Optional follow-ups" below.

| Fixture | Mode | State | Purpose |
| ------- | ---- | ----- | ------- |
| `phase-4-artifact-rewrite-pending.json` | `rewrite` | 6 diff items, all `PENDING`; `revised_document` populated with the rewritten markdown; `diff_review.direction_prompt` preserved (`"Lead with the strongest finding and tighten the structure for editors."`) | Hydrate Phase 4 after the visitor clicks `Rewrite draft`. Side-by-side view shows the candidate against the original; clicking `Apply full revision` advances to the Phase 5 rewrite fixture. |

Reference screenshots at the pinned commit:

- `phase-4-start.png` — Phase 3 handoff with both revision CTAs visible.
- `phase-4-loaded.png` — surgical diff panel loaded in inline view.
- `phase-4-surgical-top.png`, `phase-4-surgical-top2.png`, `phase-4-surgical-full.png` — surgical inline view at different scroll positions.
- `phase-4-surgical-accepted.png` — surgical inline view with several diffs accepted, `Apply full revision` enabled.
- `phase-4-surgical-applied-top.png`, `phase-4-surgical-applied-top2.png` — post-apply transition back to the workbench.
- `phase-4-rewrite-prompt.png` — rewrite direction-prompt composer (Phase 3 overlay).
- `phase-4-rewrite-generating.png`, `phase-4-rewrite-inflight.png` — loading state while the provider produces the candidate.
- `phase-4-rewrite-diff-full.png`, `phase-4-rewrite-diff-top.png` — rewrite side-by-side view.
- `phase-4-rewrite-diff-inline.png` — rewrite diff shown in inline view after toggle (note: inline rewrite is seldom used, included for UI completeness).

**What the demo needs to fake.**

- Both revision CTAs in Phase 3 are live. `Apply changes` synchronously hydrates a surgical diff-review state from the all-accepted Phase 3 fixture plus a stored surgical candidate. `Rewrite draft` opens the direction-prompt composer, accepts any non-empty string, shows a brief scripted "generating…" state, then hydrates from `phase-4-artifact-rewrite-pending.json`.
- The view toggle, per-diff `Accept` / `Reject` controls, and the `Discard revision` button are live and mutate local state only.
- `Apply full revision` does not call the backend. It swaps the in-memory artifact for the corresponding Phase 5 fixture (`phase-5-artifact-surgical.json` or `phase-5-artifact-rewrite.json`) and advances the demo.
- The auto-accept bridge from Phase 3 to Phase 4 also applies to the rewrite path: any still-`unreviewed` / `rejected` / `uncertain` agent comments flip to `accepted` before the rewrite composer opens, matching how the Phase 4 fixture was captured.

**Top-card narrative copy.**

> **Step 4 of 5 — Diff review**
>
> The agents have proposed a revision. **Surgical** mode applies only the accepted suggestions, one diff at a time — use the inline view to accept or reject each edit individually. **Rewrite** mode produces a full-document rewrite conditioned on the short direction prompt you gave; side-by-side is the right lens for reading it end-to-end, inline lets you pick hunks instead.
>
> Apply the revision to promote it to the working draft and continue to Phase 5, or discard it to return to the review workbench.

### Phase 5 — Applied revision

The visitor lands on the post-apply workbench. The working draft has been replaced by the revised markdown, and the `previous_draft_snapshot` carries the pre-apply document along with any findings that were still tied to it. New fact-check and research findings are rerun against the revised draft (in the live product); in the demo they come pre-baked from the Phase 5 fixtures.

Reference captures live in `demo-content/reference/phase-5-*.png` (rewrite variant only at the pinned commit; the surgical variant reuses `phase-4-surgical-applied-top*.png` as its working proxy — tracked under "Optional follow-ups").

**Current UI (what the visitor sees).**

- Full workbench returns. Export actions, agent chips, and the review-progress badge are back.
- `Analysis overview` renders against the revised draft.
- `Text under review` shows the **revised** document pane with any newly generated fact-check or research comments anchored to it.
- `Original-draft findings` — a collapsed-by-default disclosure panel sits below the live document. It wraps the `DocumentPane` for the previous draft plus the findings that were tied to that revision, so reviewers can re-read the agent commentary in its original context without it competing visually with the revised draft. Expanding the panel reveals the snapshot document and its threads; collapsed, the section shows only its title and a short explanatory sentence.
- Revision CTAs (`Apply changes` / `Rewrite draft`) are suppressed in the post-apply state — Phase 5 is a read-only milestone in the demo. In the live product the CTAs re-unlock as the visitor accepts new comments on the revised draft.

**Captured fixtures.**

| Fixture | Source | Notes |
| ------- | ------ | ----- |
| `phase-5-artifact-surgical.json` | Applied from the `all-accepted` Phase 3 snapshot using surgical mode with a subset of diffs accepted | Post-apply surgical working draft (~4.5 KB of revised markdown). `diff_review` is `null`, `revised_document` is `null`, `previous_draft_snapshot` preserved. |
| `phase-5-artifact-rewrite.json` | Applied from `phase-4-artifact-rewrite-pending.json` using rewrite mode with the full candidate promoted | Post-apply rewrite working draft (~5.3 KB of revised markdown). Same shape as the surgical variant. |

Reference screenshots at the pinned commit:

- `phase-5-rewrite-applied.png` — post-rewrite workbench with the revised draft in the document pane and the collapsed `Original-draft findings` panel below.
- `phase-5-rewrite-applied-verified.png` — same state, after expanding `Original-draft findings` to show the preserved previous-draft document and comments.

**What the demo needs to fake.**

- Hydrate the workbench from the Phase 5 fixture that matches the Phase 4 path the visitor took (`surgical` → `phase-5-artifact-surgical.json`; `rewrite` → `phase-5-artifact-rewrite.json`).
- The revision CTAs stay suppressed because both Phase 5 fixtures have `diff_review: null` and no Phase 5-seeded agent comments are left unreviewed in the demo snapshot.
- Export buttons (`Export Markdown`, `Export JSON`, `Export Todo`) operate on the in-memory artifact, same as Phase 3. Markdown and Todo exports are client-side serializations of the revised artifact; they do not replay captured export fixtures because Phase 5 does not ship them.
- The `Original-draft findings` disclosure is pure client state — toggling its open/closed state is live.

**Top-card narrative copy.**

> **Step 5 of 5 — Applied revision**
>
> Your revision has replaced the working draft. The revised text is on the left with any newly generated fact-check and research findings. The previous draft and the findings that were tied to it are preserved in **Original-draft findings** below — expand it whenever you need to re-read the original agent commentary in its original context.
>
> In the live product this is where you would continue a second review pass or promote the draft out of the workbench. The demo ends here — restart it from the top to try the other revision mode.

## Regenerating Fixtures

Fixtures are captured from a live local stack against the pinned commit. Re-run the steps below whenever the demo needs to track a new commit. After a full re-capture, update the `Pinned commit` line at the top of this doc and commit the refreshed fixtures alongside the doc change.

### Prerequisites

- Check out the commit you want to pin the demo to.
- Install dependencies per `docs/operations/local-development.md` (`nvm use`, repo-level `npm install`, API deps if needed).
- Start the API on its default port with `npm run dev:api`. The API serves at `http://localhost:8000`.
  - Mock provider mode is fine for preview capture (Phase 1). Later phases that capture real agent output must run with live provider keys — see each phase's subsection.
- Keep the working directory at the repo root for every snippet below. The snippets write into `demo-content/fixtures/` and read the demo article from `demo-content/`.

### Shared verification

Before any capture, confirm the backend is reachable:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/agents
```

Expected output: `200`. If not, the capture will fail — fix the backend before continuing.

### Phase 1 — `phase-1-preview.json`

Captures the parsed-document response from `POST /api/v1/sources/preview` for the demo article. The fixture hydrates the `Text under review` panel in Phase 1.

1. Ensure the fixtures directory exists:

   ```bash
   mkdir -p demo-content/fixtures
   ```

2. Post the demo article to the preview endpoint and save the response:

   ```bash
   python3 - <<'PY'
   import json, pathlib, urllib.request

   article_path = pathlib.Path("demo-content/before-you-publish-an-ai-assisted-post.md")
   article = article_path.read_text()

   payload = {
       "source_type": "text",
       "source_label": str(article_path),
       "title": None,
       "text": article,
       "content_format": "markdown",
       "url": None,
   }

   req = urllib.request.Request(
       "http://localhost:8000/api/v1/sources/preview",
       data=json.dumps(payload).encode("utf-8"),
       headers={"Content-Type": "application/json"},
       method="POST",
   )
   with urllib.request.urlopen(req) as resp:
       body = resp.read().decode("utf-8")

   out = pathlib.Path("demo-content/fixtures/phase-1-preview.json")
   out.write_text(json.dumps(json.loads(body), indent=2) + "\n")
   print(f"wrote {len(body)} bytes to {out}")
   PY
   ```

3. Verify the fixture was written with the expected shape:

   ```bash
   python3 -c "import json; d = json.load(open('demo-content/fixtures/phase-1-preview.json')); print('title:', d['title']); print('blocks:', len(d['blocks'])); print('source_type:', d['source_type'])"
   ```

   Expected output: the article title matches, `blocks` is non-zero (currently around 20 for the demo article), and `source_type` is `text`. The resulting file is roughly 20 KB.

### Phase 2 — reference screenshots only

Phase 2 is a scripted animation, not a replayed event stream, so it has no API-captured JSON fixture. What it does need is up-to-date reference screenshots of the real running view at the pinned commit, saved under `demo-content/reference/phase-2-*.png`. Re-capture these whenever the running-view UI changes meaningfully.

1. Ensure the web app (`npm run dev:web`) and API (`npm run dev:api`) are both running, with live provider keys set for the analysis provider family (mock providers produce uninteresting findings). `CONTENT_EVAL_TAVILY_API_KEY` is needed for Fact Check.
2. Open `http://localhost:3000`, paste the demo article from `demo-content/before-you-publish-an-ai-assisted-post.md`, leave all three agents selected, and click `Preview` so the `Text under review` panel loads.
3. Click `Analyze content` and capture full-page screenshots at roughly the following moments (file names match the existing captures so older ones are overwritten):
   - `phase-2-t0-launch.png` — immediately after click, `~17% COMPLETE`, Human Voice running, preview card still showing `Waiting for the first agent result.`
   - `phase-2-t15-human-voice.png` — `~50% COMPLETE`, Human Voice completed, Fact Check running, preview card rotating through Human Voice findings
   - `phase-2-t35-mid-run.png` — expand the `TOKEN USAGE` and `RUN LOG` disclosures before screenshotting so the internal structure is visible
   - `phase-2-t65-fact-check-running.png` — during the Fact Check plateau
   - `phase-2-t110-later.png` — late-stage plateau just before the Phase 3 transition
4. Let the run finish (it becomes the source for the Phase 3 terminal-artifact fixture, below).

No command-line capture is required — Phase 2 reference captures come from the browser. Playwright's `browser_take_screenshot` tool can automate this if the recapture becomes frequent.

### Phase 3 — `phase-3-artifact-*.json` and `phase-3-export-*`

Phase 3 captures three snapshots of the same artifact (`pristine`, `reviewed`, `all-accepted`). For each snapshot we save the runtime artifact JSON plus two export files (`export.md`, `export.todo.md`). We intentionally do **not** save `export.json` — it is byte-identical to the runtime artifact endpoint.

#### Prerequisites specific to Phase 3

- Live provider keys for the analysis provider family (mock providers do not produce the overlap/finding content the demo depends on).
- `CONTENT_EVAL_TAVILY_API_KEY` set — Fact Check needs it.
- The browser tab open at `http://localhost:3000` with the demo article pasted and previewed.

#### Steps

Three snapshots to capture, in order: `pristine` → `reviewed` → `all-accepted`. Each snapshot writes one artifact JSON plus two export files (`export.md`, `export.todo.md`).

1. Click `Analyze content` and wait for the run to finish. Note the artifact id — the easiest place to grab it from is `sessionStorage` in the browser devtools console:

   ```js
   JSON.parse(sessionStorage.getItem('content-evaluation:artifact')).artifactId
   ```

   Export the id into your shell as `ARTIFACT_ID` for the remaining steps.

2. Define a small capture helper (used for all three snapshots):

   ```bash
   capture_snapshot() {
     local suffix="$1"
     ARTIFACT_ID="$ARTIFACT_ID" SUFFIX="$suffix" python3 - <<'PY'
   import json, os, pathlib, urllib.request

   artifact_id = os.environ["ARTIFACT_ID"]
   suffix = os.environ["SUFFIX"]
   base = "http://localhost:8000/api/v1/runs"
   fixtures = pathlib.Path("demo-content/fixtures")
   fixtures.mkdir(exist_ok=True)

   targets = [
       (f"{base}/{artifact_id}", f"phase-3-artifact-{suffix}.json", "json"),
       (f"{base}/{artifact_id}/export.md", f"phase-3-export-{suffix}.md", "text"),
       (f"{base}/{artifact_id}/export.todo.md", f"phase-3-export-{suffix}.todo.md", "text"),
   ]
   for url, filename, kind in targets:
       with urllib.request.urlopen(url) as resp:
           body = resp.read().decode("utf-8")
       out = fixtures / filename
       if kind == "json":
           out.write_text(json.dumps(json.loads(body), indent=2) + "\n")
       else:
           out.write_text(body if body.endswith("\n") else body + "\n")
       print(f"wrote {len(body):>7} bytes to {out}")
   PY
   }
   ```

3. Capture the **pristine** snapshot (all 13 agent comments `unreviewed`, no reviewer comments yet):

   ```bash
   capture_snapshot pristine
   ```

4. Apply the seeded review states and add one standalone reviewer comment. The demo's seeded distribution is **8 accepted, 3 uncertain, 2 rejected**, picked by reading each comment's body and suggestion. A fresh pipeline run produces different comment ids, so the mapping below keys off document order (first agent comment in `threads[].comments[]`, second, etc.). Adjust per-index verdicts to taste if the comment content has shifted at the new pinned commit.

   ```bash
   ARTIFACT_ID="$ARTIFACT_ID" python3 - <<'PY'
   import json, os, pathlib, urllib.request

   artifact_id = os.environ["ARTIFACT_ID"]
   artifact = json.loads(pathlib.Path("demo-content/fixtures/phase-3-artifact-pristine.json").read_text())

   # Collect agent comments in document order.
   agent_comments = [
       c for thread in artifact["threads"] for c in thread["comments"]
       if c.get("author_type") == "agent"
   ]

   # Per-index verdicts that produced the reviewed snapshot at the current pinned commit.
   # Indices are zero-based; verify each one still makes sense against the live content.
   verdicts = [
       "accepted",   # 0: S&CR on opening
       "accepted",   # 1: Fact Check on "most of publishing workflow"
       "rejected",   # 2: Fact Check on "spread much faster"
       "accepted",   # 3: Human Voice on "Google's guidance" (loose attribution)
       "accepted",   # 4: Fact Check SUPPORTED verdict + citation ask
       "uncertain",  # 5: S&CR overlapping with Human Voice on same span
       "accepted",   # 6: Human Voice on "AI-generated writing style"
       "accepted",   # 7: Human Voice on "tidy but forgettable"
       "uncertain",  # 8: S&CR overlapping with Human Voice on same span
       "rejected",   # 9: Human Voice on "rule-of-three" (nitpick)
       "accepted",   # 10: Fact Check on "AI detectors" MIXED
       "accepted",   # 11: Human Voice on same AI detectors span
       "uncertain",  # 12: S&CR on same AI detectors span
   ]
   assert len(verdicts) == len(agent_comments), (
       f"Verdict list length ({len(verdicts)}) must match agent-comment count ({len(agent_comments)})."
   )

   for comment, state in zip(agent_comments, verdicts):
       req = urllib.request.Request(
           f"http://localhost:8000/api/v1/comments/{comment['id']}/review-state",
           data=json.dumps({"review_state": state}).encode("utf-8"),
           headers={"Content-Type": "application/json"},
           method="PATCH",
       )
       with urllib.request.urlopen(req) as resp:
           resp.read()
       print(f"  {state:>9} {comment['id']}")

   # Standalone reviewer comment anchored on the "AI detectors can help..." span.
   detector_block = next(
       b for b in artifact["document"]["blocks"]
       if "AI detectors can help with that review" in b.get("text", "")
   )
   quote = "AI detectors can help with that review because they are now fairly reliable signals"
   start = detector_block["text"].index(quote)
   payload = {
       "artifact_id": artifact_id,
       "body": (
           "I'd soften this. Calling detectors 'fairly reliable' sells their accuracy higher "
           "than the research actually supports. Consider: 'AI detectors can be one input, but "
           "their accuracy varies and they should not replace source checks.'"
       ),
       "anchor_id": None,
       "block_id": detector_block["id"],
       "start_offset": start,
       "end_offset": start + len(quote),
       "quote": quote,
   }
   req = urllib.request.Request(
       "http://localhost:8000/api/v1/comments",
       data=json.dumps(payload).encode("utf-8"),
       headers={"Content-Type": "application/json"},
       method="POST",
   )
   with urllib.request.urlopen(req) as resp:
       resp.read()
   print("  added reviewer comment")
   PY
   ```

5. Capture the **reviewed** snapshot:

   ```bash
   capture_snapshot reviewed
   ```

6. Flip every agent comment whose state is not already `accepted` to `accepted`, so the all-accepted snapshot can feed the Phase 4 capture:

   ```bash
   ARTIFACT_ID="$ARTIFACT_ID" python3 - <<'PY'
   import json, os, pathlib, urllib.request

   artifact = json.loads(pathlib.Path("demo-content/fixtures/phase-3-artifact-reviewed.json").read_text())
   for thread in artifact["threads"]:
       for c in thread["comments"]:
           if c.get("author_type") == "agent" and c["review_state"] != "accepted":
               req = urllib.request.Request(
                   f"http://localhost:8000/api/v1/comments/{c['id']}/review-state",
                   data=json.dumps({"review_state": "accepted"}).encode("utf-8"),
                   headers={"Content-Type": "application/json"},
                   method="PATCH",
               )
               with urllib.request.urlopen(req) as resp:
                   resp.read()
               print(f"  accepted {c['id']}")
   PY
   ```

7. Capture the **all-accepted** snapshot:

   ```bash
   capture_snapshot all-accepted
   ```

8. Verify the three snapshots have the expected shapes:

   ```bash
   python3 - <<'PY'
   import json, pathlib

   for suffix, expected in [
       ("pristine", {"unreviewed": 13}),
       ("reviewed", {"accepted": 8, "uncertain": 3, "rejected": 2, "unreviewed": 1}),
       ("all-accepted", {"accepted": 13, "unreviewed": 1}),
   ]:
       d = json.loads(pathlib.Path(f"demo-content/fixtures/phase-3-artifact-{suffix}.json").read_text())
       states = {}
       human = 0
       for t in d["threads"]:
           for c in t["comments"]:
               states[c["review_state"]] = states.get(c["review_state"], 0) + 1
               if c["author_type"] == "human":
                   human += 1
       total = sum(states.values())
       expected_total = sum(expected.values())
       status = "OK" if states == expected else "MISMATCH"
       print(f"{suffix:>13}: {states}  human={human}  total={total}  [{status}]")
   PY
   ```

   The `unreviewed` count in the `reviewed` and `all-accepted` snapshots comes from the single reviewer comment — human-authored comments always carry `review_state: unreviewed` because accept/reject only applies to agent comments.

### Phase 4 — `phase-4-artifact-rewrite-pending.json`

Captures the rewrite diff-review state as it appears to the visitor immediately after the rewrite candidate is generated, before any per-diff decision is made. The surgical variant is not captured pre-apply because Phase 5's surgical fixture already implies the surgical diff shape via its `previous_draft_snapshot`; if a pre-apply surgical fixture becomes useful, capture it with the same flow but skip the rewrite direction prompt.

#### Prerequisites specific to Phase 4

- Phase 3 all-accepted snapshot captured (`phase-3-artifact-all-accepted.json`) — the rewrite run keys off that artifact's id.
- Live provider keys, same as Phase 3: a real analysis provider produces the candidate rewrite; mock providers do not. `CONTENT_EVAL_TAVILY_API_KEY` is not needed for Phase 4 capture.
- The browser tab still pointed at the all-accepted artifact, or the artifact re-imported from `phase-3-artifact-all-accepted.json`.
- `ARTIFACT_ID` exported to the shell, same as Phase 3.

#### Steps

1. Open the artifact in the web app. The revision CTAs (`Apply changes` / `Rewrite draft`) should be visible at the top and bottom of the workspace.

2. Click `Rewrite draft`, paste the pinned-commit direction prompt, and generate the rewrite:

   ```
   Lead with the strongest finding and tighten the structure for editors.
   ```

   The app will open the `RevisedMarkdownPanel` in side-by-side view once the provider responds.

3. Capture the runtime artifact immediately (do not touch any `Accept` / `Reject` / view-toggle control first — the capture needs every `diff_items[].decision` to stay `pending`):

   ```bash
   ARTIFACT_ID="$ARTIFACT_ID" python3 - <<'PY'
   import json, os, pathlib, urllib.request

   artifact_id = os.environ["ARTIFACT_ID"]
   url = f"http://localhost:8000/api/v1/runs/{artifact_id}"
   with urllib.request.urlopen(url) as resp:
       body = resp.read().decode("utf-8")

   out = pathlib.Path("demo-content/fixtures/phase-4-artifact-rewrite-pending.json")
   out.write_text(json.dumps(json.loads(body), indent=2) + "\n")
   print(f"wrote {len(body)} bytes to {out}")
   PY
   ```

4. Verify the fixture has the expected shape:

   ```bash
   python3 -c "
   import json
   d = json.load(open('demo-content/fixtures/phase-4-artifact-rewrite-pending.json'))
   dr = d['diff_review']
   rd = d['revised_document']
   assert dr['mode'] == 'rewrite', dr['mode']
   assert rd['mode'] == 'rewrite', rd['mode']
   assert dr['direction_prompt'], 'direction prompt missing'
   assert all(i['decision'] == 'pending' for i in dr['diff_items']), 'expected all diffs to be pending'
   print('diff_items:', len(dr['diff_items']))
   print('direction_prompt:', dr['direction_prompt'])
   "
   ```

### Phase 5 — `phase-5-artifact-surgical.json`, `phase-5-artifact-rewrite.json`

Captures the post-apply working draft for each revision mode. The fixtures are the output of `POST /api/v1/runs/{id}/revised-markdown/apply` — same shape as the Phase 3 artifact endpoint, but with the revised document promoted into `document` and the pre-apply state preserved under `previous_draft_snapshot`.

#### Prerequisites specific to Phase 5

- Phase 3 all-accepted snapshot (for the surgical capture) and Phase 4 rewrite-pending snapshot (for the rewrite capture).
- Live provider keys, same as Phase 4.
- `ARTIFACT_ID` exported to the shell for each run.

#### Surgical variant — `phase-5-artifact-surgical.json`

1. Open the artifact from `phase-3-artifact-all-accepted.json` in the web app.

2. Click `Apply changes` to enter the surgical diff-review panel. The default view is inline.

3. Accept at least one diff so `Apply full revision` is enabled. For the pinned-commit capture we accepted three diffs that cover distinct editorial edits (opening-paragraph expansion, AI-workflow correction, Google-guidance correction); any non-empty subset is valid as long as the post-apply text still reads cleanly.

4. Click `Apply full revision`, wait for the transition back to the workbench, then capture the runtime artifact:

   ```bash
   ARTIFACT_ID="$ARTIFACT_ID" python3 - <<'PY'
   import json, os, pathlib, urllib.request

   artifact_id = os.environ["ARTIFACT_ID"]
   url = f"http://localhost:8000/api/v1/runs/{artifact_id}"
   with urllib.request.urlopen(url) as resp:
       body = resp.read().decode("utf-8")

   out = pathlib.Path("demo-content/fixtures/phase-5-artifact-surgical.json")
   out.write_text(json.dumps(json.loads(body), indent=2) + "\n")
   print(f"wrote {len(body)} bytes to {out}")
   PY
   ```

#### Rewrite variant — `phase-5-artifact-rewrite.json`

1. Start from the Phase 4 rewrite-pending state (either freshly captured or re-imported from `phase-4-artifact-rewrite-pending.json`). The diff-review panel is in side-by-side view.

2. Click `Apply full revision`. In side-by-side view the visitor does not need to accept individual diffs first — applying promotes the full rewrite candidate.

3. Capture the runtime artifact:

   ```bash
   ARTIFACT_ID="$ARTIFACT_ID" python3 - <<'PY'
   import json, os, pathlib, urllib.request

   artifact_id = os.environ["ARTIFACT_ID"]
   url = f"http://localhost:8000/api/v1/runs/{artifact_id}"
   with urllib.request.urlopen(url) as resp:
       body = resp.read().decode("utf-8")

   out = pathlib.Path("demo-content/fixtures/phase-5-artifact-rewrite.json")
   out.write_text(json.dumps(json.loads(body), indent=2) + "\n")
   print(f"wrote {len(body)} bytes to {out}")
   PY
   ```

#### Verify both variants

```bash
python3 -c "
import json
for suffix in ('surgical', 'rewrite'):
    d = json.load(open(f'demo-content/fixtures/phase-5-artifact-{suffix}.json'))
    assert d['diff_review'] is None, f'{suffix}: diff_review should be null after apply'
    assert d['revised_document'] is None, f'{suffix}: revised_document should be cleared after apply'
    assert d['previous_draft_snapshot'] is not None, f'{suffix}: previous_draft_snapshot missing'
    print(f'{suffix:>8}: raw_content_chars={len(d[\"document\"][\"raw_content\"])}, has_snapshot=True')
"
```

Expected output: both variants print a non-zero `raw_content_chars` and `has_snapshot=True`. At the pinned commit the surgical variant is ~4.5 KB and the rewrite variant is ~5.3 KB.

### Optional follow-ups

- `phase-4-artifact-surgical-pending.json` — pre-apply surgical snapshot for parity with the rewrite variant. Capture by clicking `Apply changes` on the all-accepted artifact and exporting the runtime artifact before touching any diff. The demo does not currently need this file because the surgical diff shape is recoverable from `phase-5-artifact-surgical.json`, but keeping it would make the Phase 4 fixture table symmetric.
- `phase-5-surgical-*.png` reference screenshots — the only current post-apply captures are the rewrite variant. A dedicated surgical pair (collapsed and expanded `Original-draft findings`) would round out the reference set.

