# Annotation Review Workbench

## Goal

Provide a high-legibility review surface where users can inspect source text, watch agent progress in real time, and review one canonical artifact that includes both agent and human comments.

## Target UI Regions

- Intake panel
  - URL input, file upload, pasted text, artifact import, and agent selectors
- Progress panel
  - Visually pleasing progress bar, per-agent status, stage timeline, and partial findings
- Analysis summary
  - Overall score, originality, value, audience fit, AI-likelihood
- Source text pane
  - Selectable text with highlighted spans in paragraph rows
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
- Invalid review actions should be disabled when no real artifact is loaded.

## Target Behaviors

- Highlight colors are category-based and consistent across the text pane, comment labels, and connector lines.
- Agent comments are immutable in content; reviewer input happens through replies and review-state actions.
- Reviewer comments use the `human` category and are attached to an existing or newly created anchor.
- Run status is visible in the toolbar and progress panel.
- Debug visibility should be toggleable when the artifact includes debug trace data.
- Empty states are shown when no artifact or no comment threads are present.

## Boundaries

Frontend docs should stay focused on interaction behavior and presentation.
Do not place backend prompt logic or search-provider details here.
