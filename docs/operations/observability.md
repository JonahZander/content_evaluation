# Observability

## Goal

Make every analysis run easy to inspect by humans and future agents.

## Current Visibility Requirements

- Show which agents ran
- Show which models were used
- Show start and end timestamps
- Show run status and failures
- Show evidence links from findings to spans
- Show score inputs and final synthesized outcome

## Logging Guidelines

- Logs should use stable event names and structured payloads.
- Each run should have a stable run identifier.
- First-party logs should always format safely even when third-party libraries emit records without request context.
- Each agent step should include timing and model metadata.
- User-visible conclusions should reference the source run and evidence.
- Routine successful provider transport logs should stay quiet; retry, failure, and resume signals should remain visible.

## Current Surfaces

- `/health`
  - Liveness plus app environment and processing mode
- `/ready`
  - Readiness report for database state, provider readiness, runtime mode, and persistence mode
- `RunEvent` records
  - Persisted per run and exposed both in the API payload and via SSE
- Review UI event panel
  - Human-readable event stream with stage, agent, model, and retry/resume attempt details
- Structured request logging middleware
  - Request method, path, duration, and request id

## UI Expectations

- A reviewer should be able to inspect a result without opening raw logs.
- The product should still expose enough detail for debugging suspicious outputs.
