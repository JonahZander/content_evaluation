# Multi-Agent Workflow

## Model

This project uses a code-orchestrated multi-agent model:

- one LangGraph-backed orchestrator plans and schedules the run
- specialist agents perform narrow analysis tasks
- agents do not autonomously spawn other agents
- dependencies determine execution order
- completed agent outputs are merged into one `AnalysisArtifact`

## Current Agent Roles

- Fact-check agent
  - Extracts the 3–5 most important verifiable claims from the article
  - Uses the vendored deep researcher graph (supervisor + parallel Tavily researchers) to verify each claim against live web sources
  - Returns structured claim findings: claim text, verdict, evidence summary, source links, anchor excerpt, confidence, value/differentiation notes, official-source links, and related-post links
  - Also returns summary-first overview data such as TL;DR, inferred audience, and main-claim entries for the review-summary panel
  - Also produces structured overlap research items that replace the prior standalone similarity surface in new runs
  - Multi-step execution; enabled by default because it now powers the summary panel, overlap research, and claim evidence UI
  - No dependencies on other specialist agents; runs in parallel with the independent group when selected
  - Requires CONTENT_EVAL_OPENAI_API_KEY and CONTENT_EVAL_TAVILY_API_KEY in live mode
  - Acts as the research backbone for downstream editorial reasoning
- Similarity research agent
  - Legacy compatibility path only
  - Hidden from the selectable agent catalog for new runs
- AI-likelihood agent
  - Estimates whether the text appears AI-generated
- Structure and conversion review agent
  - Produces span-level guidance on hook quality, narrative flow, skimmability, and call-to-action strength
  - Uses an adaptable framework toolkit including PAS, LEMA, AIDA, StoryBrand-style message clarity, jobs-to-be-done, and four-part blog structure heuristics instead of generic line editing
  - Consumes fact-check and AI-likelihood output explicitly
- Revised-markdown generation
  - No longer runs as a first-pass agent
  - Consumes accepted suggestions after the main run to produce a candidate revised markdown plus diff-review data

## Agent Definition Shape

Each agent should be declared with:

- `agent_id`
- `display_name`
- `category`
- `depends_on`
- `provider_kind`
- `execution_mode`
- `instruction_file`
- `result_schema`
- optional provider/model routing metadata

## Execution Rules

- Selected agents are explicit in the API and UI.
- Required dependencies are auto-included.
- Independent agents may run in parallel.
- Dependent agents wait for prerequisites.
- New-run dependency graph is:
  - `fact_check` and `ai_likelihood` can start independently
  - `editorial` waits for `fact_check` and `ai_likelihood`
- `value`, `audience`, and first-pass `synthesis` are no longer scheduled for new runs
- Each status transition emits a durable event for the live timeline.
- Each completed node writes a resumable graph checkpoint.

## Instruction Organization

- Agent instructions live in their own folder under the API package.
- Each agent should point at one instruction file, but that file may live in a nested subdirectory such as `fact_check/research_brief.md`.
- Provider code should load instruction text from those files instead of embedding prompts inline.
- Adding an agent should mainly require:
  - one instruction file
  - one schema
  - one registry entry
  - optional dependencies

## Shared Inputs

- Normalized document text
- Ordered document blocks
- Source metadata
- Upstream agent outputs when a dependency exists
- Run configuration including selected agents and debug settings
- Internal graph checkpoint state for resuming interrupted runs

## Shared Outputs

- Structured results per agent
- Evidence references to anchors/spans
- Confidence indicators
- Recommended actions
- Model/provider metadata
- Partial and final artifact snapshots

## Design Principles

- Each agent should have a clear contract and a narrow job.
- Agents should emit structured data before any user-facing prose.
- Artifact assembly should happen in code, not inside prompts.
- Agent outputs should be inspectable in the UI and exportable for debugging.
- Agent comments should remain immutable; reviewer feedback happens via replies and review-state actions inside the same artifact.
- Not every agent should produce comment-rail surface area. Fact-check is summary/evidence-first by default, while AI-likelihood and editorial remain comment-producing.

## Current Provider Routing

- Deep research (fact_check agent)
  - Vendored deep researcher graph (supervisor + parallel researchers + Tavily) in live mode
  - MockDeepResearchProvider in development/test fallback
  - Source: vendors/adapted from langchain-ai/open_deep_research (MCP stripped, CONTENT_EVAL key support added)
- Similarity search
  - Tavily in live mode
  - Mock search provider in development/test fallback
- Content extraction
  - Direct fetch + Trafilatura first in live mode
  - Tavily extract fallback for blocked or unreadable URLs
  - Mock extractor in development/test fallback
- Analysis categories
  - LangChain-routed OpenAI, Anthropic, or Gemini in live mode
  - Mock deterministic analysis provider in development/test fallback
