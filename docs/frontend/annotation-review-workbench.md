# Annotation Review Workbench

## Goal

Provide a high-legibility review surface where users can inspect source text, watch agent progress in real time, and review one canonical artifact that includes both agent and human comments.

## Target UI Regions

- Intake panel
  - URL input with explicit draft-import preview, file upload, pasted text, artifact import, and agent selectors
- Progress panel
  - Visually pleasing progress bar, per-agent status, stage timeline, retry/resume notices, and partial findings
- Run log
  - Full-width activity list directly below the progress panel so users can inspect retries, resumptions, and failures without leaving the main flow
- Analysis summary
  - Overall score, originality, value, audience fit, AI-likelihood
- Source text pane
  - Selectable text with highlighted spans in paragraph rows
  - Supports lightweight markdown presentation for headings, inline emphasis, and fenced code blocks
- Comment area
  - Each paragraph row owns its own right-side comment stack so later text does not continue until that paragraph's comments end
- Token usage panel (`AgentUsageSummary`)
  - Per-agent table of input tokens, output tokens, and estimated USD cost; only rendered when usage data is present
- Optional debug panel
  - Downloadable trace details when debug output is enabled

## Implementation Notes

- `ReviewWorkbench.tsx` coordinates run submission, artifact import/export, live progress, and review mutations against artifact snapshots using a centralized `useReducer` + typed action dispatch instead of individual `useState` hooks.
- State shape, actions, and the pure reducer live in `src/components/review/workbench-state.ts` so state transitions are explicit and testable.
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
- Comments identify the agent or reviewer that produced them.
- Agent comments are replyable by the human reviewer.
- Agent comments expose immediate `Accept`, `Reject`, and `Uncertain` actions, and clicking the active state again should clear it back to `unreviewed`.
- Human standalone comments can be edited or deleted inline.
- Human replies should expose a compact delete affordance in the thread UI.
- Partial findings should appear as each agent finishes instead of waiting for the full run.
- Hovering or selecting a summary finding should highlight linked spans in the source text.
- Connector lines should visually link each comment card to the relevant highlight.
- Multiple comments on the same span should stack vertically while connecting back to the same text selection.
- Overlapping anchors must render from one shared set of text segments so source text is never duplicated in the document pane.
- Multi-block anchors must render continuation highlights in later adjacent rows without duplicating the same thread card.
- Paragraphs with comments should reserve the vertical space needed for those comments before the next paragraph begins.
- Export and import actions should be visible from the main toolbar.
- The toolbar should expose JSON, Markdown, and compact Markdown todo exports from the main action row.
- The toolbar should expose a stop-run action for queued/running work and a new-analysis reset action.
- The toolbar should keep the pasted-text composer in its own full-width source row beneath source selection controls.
- Invalid review actions should be disabled when no real artifact is loaded.

## Target Behaviors

- Highlight colors are category-based and consistent across the text pane, comment labels, and connector lines.
- When multiple agents or anchor ranges overlap on the same visible text, render one neutral highlight fill with thin agent-color rails instead of layered color overlays.
- Supported markdown rendering is intentionally narrow in v1:
  - headings
  - `strong`
  - `em`
  - fenced code blocks
- URL mode should not display the pasted-text textarea because analysis runs from the imported URL preview content.
- Unsupported markdown should stay readable as text rather than render rich embeds or media.
- Agent comments are immutable in content; reviewer input happens through replies and review-state actions.
- Reviewer comments use the `human` category and are attached to an existing or newly created anchor.
- Reviewer replies can be deleted inline, but agent-authored content remains immutable.
- Run status is visible in the toolbar and progress panel.
- Queued or running progress bars should animate even while the percentage is unchanged so the reviewer can see that work is still active.
- Retry and resume events should be visible in both the run log and the per-agent status area.
- Starting a new analysis should warn before discarding a not-yet-downloaded JSON artifact.
- The `New analysis` button should only appear once a real artifact exists.
- Todo export should include only accepted agent suggestions, ordered by where they appear in the article, with a compact checklist followed by short context that includes both the original agent comment and the suggested change.
- Debug visibility should be toggleable when the artifact includes debug trace data.
- Empty states are shown when no artifact or no comment threads are present.
- Synthetic unmatched-reference blocks should render with visibly distinct fallback styling so reviewers can tell they are not original article text.
- When an anchor cannot be matched into one contiguous set of adjacent rendered blocks, its thread should render after the article in an unmatched-reference section instead of attaching to the first paragraph.

## Boundaries

Frontend docs should stay focused on interaction behavior and presentation.
Do not place backend prompt logic or search-provider details here.
