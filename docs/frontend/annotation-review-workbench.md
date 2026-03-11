# Annotation Review Workbench

## Goal

Provide a high-legibility review surface where users can inspect source text, watch agent progress in real time, and review one canonical artifact that includes both agent and human comments.

## Target UI Regions

- Intake panel
  - URL input with explicit draft-import preview, file upload, pasted text, artifact import, and agent selectors
- Progress panel
  - Visually pleasing progress bar, per-agent status, stage timeline, and partial findings
- Analysis summary
  - Overall score, originality, value, audience fit, AI-likelihood
- Source text pane
  - Selectable text with highlighted spans in paragraph rows
  - Supports lightweight markdown presentation for headings, inline emphasis, and fenced code blocks
- Comment area
  - Each paragraph row owns its own right-side comment stack so later text does not continue until that paragraph's comments end
- Optional debug panel
  - Downloadable trace details when debug output is enabled

## Target Implementation Notes

- `ReviewWorkbench.tsx` should coordinate run submission, artifact import/export, live progress, and review mutations against artifact snapshots.
- Presentational review pieces live under `src/components/review/`.
- Connector lines are rendered inside each paragraph row so the anchor-to-comment mapping remains local and legible.
- The workbench uses paragraph-scoped rows so each source block and its comments stay spatially linked.
- The UI should render directly from the artifact snapshot rather than a stitched backend-only view model.

## Key Interaction Patterns

- Selecting a text span opens a reviewer comment composer for a new standalone human comment.
- URL sources should be imported and previewed before analysis starts so the reviewer can inspect the normalized draft first.
- Comments identify the agent or reviewer that produced them.
- Agent comments are replyable by the human reviewer.
- Agent comments expose immediate `Accept`, `Reject`, and `Uncertain` actions.
- Human standalone comments can be edited or deleted inline.
- Partial findings should appear as each agent finishes instead of waiting for the full run.
- Hovering or selecting a summary finding should highlight linked spans in the source text.
- Connector lines should visually link each comment card to the relevant highlight.
- Multiple comments on the same span should stack vertically while connecting back to the same text selection.
- Paragraphs with comments should reserve the vertical space needed for those comments before the next paragraph begins.
- Export and import actions should be visible from the main toolbar.
- The toolbar should expose a stop-run action for queued/running work and a new-analysis reset action.
- Invalid review actions should be disabled when no real artifact is loaded.

## Target Behaviors

- Highlight colors are category-based and consistent across the text pane, comment labels, and connector lines.
- Supported markdown rendering is intentionally narrow in v1:
  - headings
  - `strong`
  - `em`
  - fenced code blocks
- URL mode should not display the pasted-text textarea because analysis runs from the imported URL preview content.
- Unsupported markdown should stay readable as text rather than render rich embeds or media.
- Agent comments are immutable in content; reviewer input happens through replies and review-state actions.
- Reviewer comments use the `human` category and are attached to an existing or newly created anchor.
- Run status is visible in the toolbar and progress panel.
- Starting a new analysis should warn before discarding a not-yet-downloaded JSON artifact.
- Debug visibility should be toggleable when the artifact includes debug trace data.
- Empty states are shown when no artifact or no comment threads are present.
- When an anchor cannot be matched to a rendered block, its thread should render after the article in an unmatched-reference section instead of attaching to the first paragraph.

## Boundaries

Frontend docs should stay focused on interaction behavior and presentation.
Do not place backend prompt logic or search-provider details here.
