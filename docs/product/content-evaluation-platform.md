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
- Fact-check findings with linked evidence and overlap research
- AI-generation likelihood estimate
- Fact-check-backed review summary data such as TL;DR, inferred audience, overlap items, and overall review metrics
- Section-level editorial comments and revision suggestions anchored to text spans
- Targeted follow-up research appended to an existing artifact
- Threaded reviewer replies beneath agent comments
- Reviewer decisions on agent comments: `accepted`, `rejected`, `uncertain`
- Evidence trail showing run events, agent stages, and model names
- Todo Markdown, full Markdown, and JSON exports
- Optional debug/trace information about agent execution

## Primary User Flow

1. User submits content or imports an existing artifact.
2. The API creates an artifact plus run config, including selected agents and persistence mode.
3. The system normalizes the text into a shared document model with ordered blocks.
4. A LangGraph-backed orchestrator expands agent dependencies, resumes from checkpoints when needed, schedules agents in dependency order, and merges each result into the artifact.
5. The UI shows live progress, partial findings, summary data, anchored comments, and export actions.
6. The reviewer replies to comments, marks agent comments accepted/rejected/uncertain, can add standalone comments on selected text, and can trigger revised-markdown generation after accepting suggestions.
7. The artifact can be exported, re-imported, or persisted in workspace mode.

## Product Principles

- Every high-level judgment should link back to evidence.
- The review surface should make span-level comments easy to inspect and act on.
- Agent outputs should be traceable by agent, model, event, and reasoning category.
- Final scoring should synthesize multiple signals instead of relying on a single heuristic.
- The API should remain useful without the frontend by producing a complete artifact directly.
- The analysis layer should be portable across OpenAI, Anthropic, and Gemini without changing review logic.
- Local/open-source use should work in session mode without requiring a database.
- Artifact JSON export/import should stay stable enough to reopen prior reviews without special runtime-only data.
- Production should fail fast rather than silently dropping to mock behavior.

## Current Non-Goals

- Full user authentication and per-user permissions
- Rich text editing of the source article inside the app
- Support for formats beyond URL, `.txt`, and `.md`
- Autonomous agent spawning or free-form agent-to-agent planning
