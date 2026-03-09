# Observability

## Goal

Make every analysis run easy to inspect by humans and future agents.

## Planned Visibility Requirements

- Show which agents ran
- Show which models were used
- Show start and end timestamps
- Show run status and failures
- Show evidence links from findings to spans
- Show score inputs and final synthesized outcome

## Logging Guidelines

- Logs should use stable event names and structured payloads.
- Each run should have a stable run identifier.
- Each agent step should include timing and model metadata.
- User-visible conclusions should reference the source run and evidence.

## UI Expectations

- A reviewer should be able to inspect a result without opening raw logs.
- The product should still expose enough detail for debugging suspicious outputs.
