# Annotation Review Workbench

## Goal

Provide a high-legibility review surface where users can inspect the source text, select spans, review agent comments, and compare summary judgments with supporting evidence.

## Current UI Regions

- Intake panel
  - URL input, file upload, or pasted text
- Analysis summary
  - Overall score, originality, value, audience fit, AI-likelihood
- Source text pane
  - Selectable text with highlighted spans on the left
- Comment rail
  - Comments, threaded replies, review-state buttons, and rationale on the right
- Run details panel
  - Run events with stage, agent name, model name, and status

## Current Implementation Notes

- `ReviewWorkbench.tsx` coordinates run submission, live refresh, inline comment editing, replies, exports, and connector measurement.
- Presentational review pieces live under `src/components/review/`.
- Connector lines are rendered as a shared SVG overlay spanning the full workspace.
- The workbench uses one visual workspace so text highlights and comment cards can be linked spatially.

## Key Interaction Patterns

- Selecting a text span opens a reviewer comment composer for a new standalone human comment.
- Comments should identify the agent or reviewer that produced them.
- Agent comments should be replyable by the human reviewer.
- Agent comments should expose immediate `Accept`, `Reject`, and `Uncertain` actions.
- Human standalone comments can be edited or deleted inline.
- Hovering or selecting a summary finding should highlight linked spans in the source text.
- Users should be able to tell which findings are direct evidence and which are synthesis.
- Connector lines should visually link each comment card to the relevant highlight.
- Multiple comments on the same span should stack vertically while connecting back to the same text selection.
- Export actions should always be visible from the main toolbar.

## Current Behaviors

- Highlight colors are category-based and consistent across the text pane, comment labels, and connector lines.
- Agent comments are immutable in content; reviewer input happens through replies and review-state actions.
- Reviewer comments use the `human` category and are attached to an existing or newly created anchor.
- Run status is visible in the toolbar and summary panel.
- Empty states are shown when no document or no comment threads are present.

## Boundaries

Frontend docs should stay focused on interaction behavior and presentation.
Do not place backend prompt logic or search-provider details here.
