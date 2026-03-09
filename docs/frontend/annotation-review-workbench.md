# Annotation Review Workbench

## Goal

Provide a high-legibility review surface where users can inspect the source text, select spans, review agent comments, and compare summary judgments with supporting evidence.

## Planned UI Regions

- Intake panel
  - URL input, file upload, pasted-text tab
- Analysis summary
  - Overall score, originality, value, audience fit, AI-likelihood
- Source text pane
  - Selectable text with highlighted spans
- Comment rail
  - Comments, suggestions, and rationale attached to spans
- Run details panel
  - Agent steps, model usage, timestamps, and status

## Key Interaction Patterns

- Selecting a text span should reveal existing comments and allow new comments later.
- Comments should identify the agent or reviewer that produced them.
- Suggestions should support categories like cut, rewrite, clarify, support, or retarget.
- Hovering or selecting a summary finding should highlight linked spans in the source text.
- Users should be able to tell which findings are direct evidence and which are synthesis.

## Boundaries

Frontend docs should stay focused on interaction behavior and presentation.
Do not place backend prompt logic or search-provider details here.
