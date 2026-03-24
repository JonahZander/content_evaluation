# Annotation Review Workbench

## Goal

Provide a high-legibility review surface where users can inspect source text, watch agent progress in real time, and review one canonical artifact that includes both agent and human comments.

## Target UI Regions

- Intake panel
  - URL input with explicit draft-import preview, file upload, pasted text, artifact import, and agent selectors
- Progress panel
  - Phase-2-only running view with progress bar, per-agent status, stage timeline, retry/resume notices, partial findings, and run log
- Run log
  - Full-width activity list inside the running view so users can inspect retries, resumptions, and failures without leaving Phase 2
- Analysis summary
  - Overall score, novelty, AI-likelihood, TL;DR, and article-length overview metrics shown only in the terminal review phase
- Review summary panel
  - Lives above the source text pane in Phase 3 only
  - Shows TL;DR, article profile, structural completeness, main claims, inferred audience, research summary, and overlap links from fact-check-backed artifact data
- Revised markdown panel
  - Lives in an isolated Phase 4 shell once a candidate revision exists
  - Shows original cleaner-output markdown, candidate revised markdown, deterministic diff items, and per-diff reviewer decisions before the working draft is replaced
- Source text pane
  - Selectable text with highlighted spans in paragraph rows
  - Supports lightweight markdown presentation for headings, inline emphasis, inline links, and fenced code blocks
- Comment area
  - Each paragraph row owns its own right-side comment stack so later text does not continue until that paragraph's comments end
  - Agent comment cards should stay compact when multiple comments target the same section
- Token usage panel (`AgentUsageSummary`)
  - Per-agent table of input tokens, output tokens, and estimated USD cost; only rendered when usage data is present
  - Multi-model deep research runs should show `mixed` in the model column with a compact per-model token and cost breakdown underneath
- Optional debug panel
  - Downloadable trace details when debug output is enabled
- Phase shells
  - Phase 1 shows only intake/import controls plus any URL or draft preview
  - Phase 2 shows only the running view and does not render the full workbench behind it
  - Phase 3 shows the review workbench, metrics, summary, source pane, and inline comment rail
  - Phase 4 isolates revised-markdown diff review until all diff decisions are recorded

## Implementation Notes

- `ReviewWorkbench.tsx` coordinates run submission, artifact import/export, live progress, and review mutations against artifact snapshots using a centralized `useReducer` + typed action dispatch instead of individual `useState` hooks.
- State shape, actions, and the pure reducer live in `src/components/review/workbench-state.ts` so state transitions are explicit and testable.
- Phase selection is derived from the current artifact state so imported draft, running, terminal, and diff-review artifacts restore into the right shell.
- Key callbacks (`refreshArtifact`, `refreshArtifactCoalesced`) are stabilized with `useCallback` so the SSE effect always references the current version.
- The `SelectionDraft` interface is defined once in `src/lib/types.ts` and imported by `ReviewWorkbench`, `SelectionBanner`, and `DocumentPane`.
- Presentational review pieces live under `src/components/review/`.
- Connector lines are rendered inside each paragraph row so the anchor-to-comment mapping remains local and legible.
- The workbench uses paragraph-scoped rows so each source block and its comments stay spatially linked.
- Adjacent multi-block agent anchors should highlight every linked source segment while keeping the thread card attached to the first block row.
- The UI should render directly from the artifact snapshot rather than a stitched backend-only view model.

## Key Interaction Patterns

- Selecting a text span opens a reviewer comment composer for a new standalone human comment.
- URL sources should be imported and previewed before analysis starts so the reviewer can inspect the normalized draft first.
- Imported URL previews should support reversible per-block removal before analysis so boilerplate or irrelevant sections can be excluded without editing the raw draft.
- Imported URL previews should keep removed blocks in place with muted styling and a remove/restore toggle so the layout does not shift while the reviewer prunes the draft.
- URL preview pruning stays in Phase 1 so the reviewer can normalize the draft before the first run.
- Workspace persistence should be the preselected mode for new analyses so reloads can recover the canonical artifact from the backend.
- Session persistence should remain available as a lightweight local option, but the browser should only store restore metadata rather than a full artifact snapshot.
- Comments identify the agent or reviewer that produced them.
- Agent comments are replyable by the human reviewer.
- Agent comments expose immediate `Accept`, `Reject`, and `Uncertain` actions, and clicking the active state again should clear it back to `unreviewed`.
- Agent comments should expose an `Add comment` action in the same compact action row as `Accept`, `Reject`, and `Uncertain`, revealing the reply field only on demand.
- Completed, failed, or canceled artifacts should support additive follow-up analysis on the same artifact instead of forcing a new run.
- Terminal artifacts with accepted agent suggestions should expose a `Generate revised markdown` action.
- Once revised markdown exists, the reviewer must accept or reject every diff item before the reviewed markdown can be applied.
- Follow-up analysis should stay blocked while revised-markdown diff review is pending or waiting to be applied.
- Human standalone comments can be edited or deleted inline.
- Human replies should expose a compact trash delete affordance in the thread UI.
- Partial findings should appear as each agent finishes instead of waiting for the full run.
- Hovering or selecting a summary finding should highlight linked spans in the source text.
- Highlighted spans should stay visually continuous even when the underlying text contains inline markdown links.
- Fact-check claim highlights should render distinct evidence chips near the relevant paragraph instead of creating more comment-rail cards.
- Connector lines should visually link each comment card to the relevant highlight.
- Connector lines should recalculate after thread/document/layout changes and should avoid resize-jank during rapid window resizing.
- Multiple comments on the same span should stack vertically while connecting back to the same text selection.
- Overlapping anchors must render from one shared set of text segments so source text is never duplicated in the document pane.
- Multi-block anchors must render continuation highlights in later adjacent rows without duplicating the same thread card.
- Paragraphs with comments should reserve the vertical space needed for those comments before the next paragraph begins.
- Export and import actions should be visible from the main toolbar.
- The toolbar should expose JSON, Markdown, and compact Markdown todo exports from the main action row.
- The toolbar should expose revised-markdown generation only when accepted agent suggestions exist and no diff review is already active.
- The toolbar should expose a stop-run action for queued/running work and a new-analysis reset action.
- The toolbar should keep the pasted-text composer in its own full-width source row beneath source selection controls.
- Invalid review actions should be disabled when no real artifact is loaded.
- Similarity research is no longer a selectable top-level agent in new runs; overlap research is surfaced through fact-check.

## Target Behaviors

- Highlighted text should stay neutral by default so dense clusters remain legible, with agent color becoming prominent on hover or focus from the linked thread.
- Connector lines should stay subtle by default and bring forward the linked agent color on hover or focus.
- When multiple agents or anchor ranges overlap on the same visible text, render one neutral highlight fill rather than layered color overlays.
- Fact-check evidence should stay lightweight: one compact chip row or small stacked evidence block beside the paragraph, capped to a few links.
- Supported markdown rendering is intentionally narrow in v1:
  - headings
  - `strong`
  - `em`
  - inline links
  - fenced code blocks
- URL mode should not display the pasted-text textarea because analysis runs from the imported URL preview content.
- URL preview pruning is preview-only: excluded blocks stay visible in place with subdued styling, are omitted from the pending run, can be restored before analysis, and do not mutate persisted artifact state before a run starts.
- Unsupported markdown should stay readable as text rather than render rich embeds or media.
- Agent comments are immutable in content; reviewer input happens through replies and review-state actions.
- Audience analysis is summary-first in the current UI and should not create new inline annotation-heavy threads for newly generated artifacts.
- The review summary panel should be fact-check-backed and compact rather than recreating old standalone value or audience agent surfaces.
- Reviewer comments use the `human` category and are attached to an existing or newly created anchor.
- Reviewer replies can be deleted inline, but agent-authored content remains immutable.
- Run status is visible in the toolbar and progress panel.
- Queued or running progress bars should animate even while the percentage is unchanged so the reviewer can see that work is still active.
- Retry and resume events should be visible in both the run log and the per-agent status area.
- Partial findings should rotate in a focused running preview card during Phase 2 rather than exposing the full workbench.
- Append-agent runs should keep the review shell visible and surface only a compact inline progress strip while they are active.
- Terminal artifacts should switch the primary action to `Add selected analysis`, disable already completed agents, and queue only newly selected follow-up analysis.
- Starting a new analysis should warn before discarding a not-yet-downloaded JSON artifact.
- The `New analysis` button should only appear once a real artifact exists.
- Todo export should include only accepted agent suggestions, ordered by where they appear in the article, with a compact checklist followed by short context that includes both the original agent comment and the suggested change.
- Revised markdown should remain a post-run, reviewer-triggered workflow; the canonical draft changes only after reviewed diff decisions are applied.
- Debug visibility should be toggleable when the artifact includes debug trace data.
- Empty states are shown when no artifact or no comment threads are present.
- Synthetic unmatched-reference blocks should render with visibly distinct fallback styling so reviewers can tell they are not original article text.
- When an anchor cannot be matched into one contiguous set of adjacent rendered blocks, its thread should render after the article in an unmatched-reference section instead of attaching to the first paragraph.
- Revised-markdown diff review is isolated from the main workbench until all diff decisions are recorded and the revision is applied.

## Boundaries

Frontend docs should stay focused on interaction behavior and presentation.
Do not place backend prompt logic or search-provider details here.
