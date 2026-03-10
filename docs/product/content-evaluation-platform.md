# Content Evaluation Platform

## Problem

Writers and editors need a fast way to judge whether a blog post is original, useful, targeted, and worth a reader's time.

## Current Inputs

- Blog post URL
- Uploaded `.txt` or `.md` file
- Pasted raw text
- Imported artifact JSON

## Current Outputs

- Canonical `AnalysisArtifact` snapshots that can be created without the frontend
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
- Optional debug/trace information about agent execution

## Primary User Flow

1. User submits content or imports an existing artifact.
2. The API creates a session-oriented artifact and a run config, including selected agents.
3. The system normalizes the text into a shared document model with ordered blocks.
4. An orchestrator expands agent dependencies, runs independent agents in parallel, waits for prerequisite-driven agents, and merges each result into the artifact.
5. The UI shows live progress, partial findings, summary data, anchored comments, and export actions.
6. The reviewer replies to comments, marks agent comments accepted/rejected/uncertain, and can add standalone comments on selected text.
7. The artifact can be exported, re-imported, or optionally persisted in workspace mode.

## Product Principles

- Every high-level judgment should link back to evidence.
- The review surface should make span-level comments easy to inspect and act on.
- Agent outputs should be traceable by agent, model, event, and reasoning category.
- Final scoring should synthesize multiple signals instead of relying on a single heuristic.
- The API should remain useful without the frontend by producing a complete artifact directly.
- Local/open-source use should work in session mode without requiring a database.
- Production should fail fast rather than silently dropping to mock behavior.

## Current Non-Goals

- Full user authentication and per-user permissions
- Rich text editing of the source article inside the app
- Support for formats beyond URL, `.txt`, and `.md`
- Autonomous agent spawning or free-form agent-to-agent planning
