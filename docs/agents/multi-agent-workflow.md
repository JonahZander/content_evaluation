# Multi-Agent Workflow

## Current Agents

- Similarity research agent
  - Searches online for related posts and overlap in claims or framing
- AI-likelihood agent
  - Estimates whether the text appears AI-generated
- Value extraction agent
  - Identifies the main value proposition and key takeaways
- Audience analysis agent
  - Infers the target audience and fit
- Editorial recommendation agent
  - Converts findings into span-level comments and rewrite suggestions
- Evaluation synthesis agent
  - Produces the final reading-worthiness assessment

## Shared Inputs

- Normalized document text
- Document blocks
- Section and span identifiers
- Source metadata
- Similarity results when synthesis needs them

## Shared Outputs

- Structured findings
- Evidence references to spans
- Confidence indicators
- Recommended actions
- Run metadata including model and timestamps
- Top-level anchored comments for the review UI

## Design Principles

- Each agent should have a clear contract and a narrow job.
- Agents should emit structured data before any user-facing prose.
- Synthesis should happen after specialized analysis, not instead of it.
- Agent outputs should be inspectable in the UI.
- Agent comments should remain immutable; reviewer feedback happens via replies and review-state actions.

## Current Provider Routing

- Similarity search
  - Tavily in live mode
  - Mock search provider in development/test fallback
- Content extraction
  - Trafilatura-backed extraction provider in live mode
  - Mock extractor in development/test fallback
- Analysis categories
  - OpenAI in live mode
  - Mock deterministic analysis provider in development/test fallback
