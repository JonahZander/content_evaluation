# Analysis Pipeline

## Goal

Turn raw content into structured, explainable analysis that powers the review UI.

## Planned Stages

1. Intake
   - Accept URL, uploaded file, or pasted text
2. Normalization
   - Extract text and metadata into a shared document schema
3. Preprocessing
   - Chunk text, detect sections, and generate span identifiers
4. Agent execution
   - Run specialized analyses in parallel where possible
5. Aggregation
   - Merge findings, deduplicate overlap, and compute final scores
6. Persistence
   - Store runs, traces, comments, and synthesized outputs

## Planned Services

- Ingestion service
- Document normalization service
- Similar-content search service
- AI-likelihood analysis service
- Value and audience analysis service
- Recommendation synthesis service
- Evaluation scoring service
- Run logging service

## Boundaries

- Provider-specific details should live near adapters, not in orchestration logic.
- Shared document schemas should be stable and explicit.
- Aggregation should preserve evidence links back to spans and agent runs.
