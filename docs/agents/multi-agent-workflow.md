# Multi-Agent Workflow

## Planned Agents

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

## Expected Shared Inputs

- Normalized document text
- Section and span identifiers
- Source metadata
- Prior agent outputs when explicitly required

## Expected Shared Outputs

- Structured findings
- Evidence references to spans
- Confidence indicators
- Recommended actions
- Run metadata including model and timestamps

## Design Principles

- Each agent should have a clear contract and a narrow job.
- Agents should emit structured data before any user-facing prose.
- Synthesis should happen after specialized analysis, not instead of it.
- Agent outputs should be inspectable in the UI.
