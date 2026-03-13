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
  - Returns one finding per claim: verdict (SUPPORTED/REFUTED/MIXED/UNVERIFIABLE), key evidence, and source URLs in the rationale
  - Also produces a redundancy/differentiation finding: flags overlap with existing public posts and notes where the article adds unique value
  - Multi-step execution; opt-in (default_enabled=False) due to cost
  - No dependencies on other specialist agents; runs in parallel with the independent group when selected
  - Requires CONTENT_EVAL_OPENAI_API_KEY and CONTENT_EVAL_TAVILY_API_KEY in live mode
  - The similarity agent remains the fast/cheap option; fact_check is the deep/comprehensive option
- Similarity research agent
  - Searches online for related posts and overlap in claims or framing
  - Can be multi-step because research may require intermediate search reasoning
- AI-likelihood agent
  - Estimates whether the text appears AI-generated
- Value extraction agent
  - Identifies the main value proposition and key takeaways
- Audience analysis agent
  - Infers the target audience and fit
- Editorial recommendation agent
  - Produces span-level comments and rewrite suggestions
- Evaluation synthesis agent
  - Produces a final verdict after upstream specialist agents complete

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
- Synthesis/scoring runs after upstream specialist agents finish.
- Each status transition emits a durable event for the live timeline.
- Each completed node writes a resumable graph checkpoint.

## Instruction Organization

- Agent instructions live in their own folder under the API package.
- One instruction file should exist per agent.
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
