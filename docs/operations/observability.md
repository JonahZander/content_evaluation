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
- Show per-agent token usage (input and output tokens)
- Show estimated cost per agent and run total

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
- Review UI token usage panel (`AgentUsageSummary`)
  - Per-agent table of input tokens, output tokens, and estimated USD cost
  - Totals row across all agents that reported usage
  - Model names truncated to 28 characters with full name on hover
  - Deep research runs that use more than one model should render as `mixed` with a per-model token and cost breakdown under the primary label
  - Cost estimation uses the hardcoded OpenAI pricing table in `apps/web/src/lib/pricing.ts`; unknown models still show `—`
- Structured request logging middleware
  - Request method, path, duration, and request id

## Token Usage and Cost

- `AgentExecutionResult` carries a `usage` field (`{ input_tokens, output_tokens }`) populated by each provider after its LLM call completes.
- The LangChain provider reads token counts from the `AIMessage` response metadata.
- The deep research and mock providers populate usage directly.
- Orchestration threads `usage` into `ArtifactAgentResult.metadata` so the frontend can read it without touching raw backend state.
- The `AgentUsageSummary` component reads `metadata.usage` from each agent result and renders the per-agent table.
- Deep research also persists `metadata.usage_by_model` so the frontend can price mixed-model runs from exact per-model token counts instead of a placeholder.
- Cost estimation is best-effort: if a model name does not match the pricing table that model shows `—` rather than a wrong number.

## UI Expectations

- A reviewer should be able to inspect a result without opening raw logs.
- The product should still expose enough detail for debugging suspicious outputs.
- The token usage panel should only appear when at least one agent result includes usage data.
