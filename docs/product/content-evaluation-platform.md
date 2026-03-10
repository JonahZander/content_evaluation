# Content Evaluation Platform

## Problem

Writers and editors need a fast way to judge whether a blog post is original, useful, targeted, and worth a reader's time.

## Current Inputs

- Blog post URL
- Uploaded `.txt` or `.md` file
- Pasted raw text

## Current Outputs

- Similar-content findings from online research
- AI-generation likelihood estimate
- Main value proposition summary
- Likely target audience
- Reading-worthiness evaluation
- Section-level comments and revision suggestions anchored to text spans
- Threaded reviewer replies beneath agent comments
- Reviewer decisions on agent comments: `accepted`, `rejected`, `uncertain`
- Evidence trail showing run events, agent stages, and model names
- Markdown and JSON exports

## Primary User Flow

1. User submits content through one of the supported inputs.
2. The API creates a queued run and the worker processes it asynchronously.
3. The system normalizes the text into a shared document model with ordered blocks.
4. Specialized agents analyze the document for similarity, AI likelihood, value, audience, editorial suggestions, and synthesis.
5. The UI shows summary scores, anchored comments, run events, and export actions.
6. The reviewer replies to comments, marks agent comments accepted/rejected/uncertain, and can add standalone comments on selected text.

## Product Principles

- Every high-level judgment should link back to evidence.
- The review surface should make span-level comments easy to inspect and act on.
- Agent outputs should be traceable by run, model, and reasoning category.
- Final scoring should synthesize multiple signals instead of relying on a single heuristic.
- Local development should remain usable without live provider keys.
- Production should fail fast rather than silently dropping to mock behavior.

## Current Non-Goals

- Full user authentication and per-user permissions
- Rich text editing of the source article inside the app
- Support for formats beyond URL, `.txt`, and `.md`
- External job queue infrastructure beyond the current repository-backed worker
