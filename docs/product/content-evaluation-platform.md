# Content Evaluation Platform

## Problem

Writers and editors need a fast way to judge whether a blog post is original, useful, targeted, and worth a reader's time.

## Planned Inputs

- Blog post URL
- Uploaded text file
- Pasted raw text

## Planned Outputs

- Similar-content findings from online research
- AI-generation likelihood estimate
- Main value proposition summary
- Likely target audience
- Reading-worthiness evaluation
- Section-level comments and revision suggestions
- Evidence trail showing what agents did and which models were used

## Primary User Flow

1. User submits content through one of the supported inputs.
2. The system normalizes the text into a common document model.
3. Specialized agents analyze the document from different angles.
4. The UI shows summary scores, evidence, and section-level annotations.
5. The user reviews suggested cuts, rewrites, or focus improvements.

## Product Principles

- Every high-level judgment should link back to evidence.
- The review surface should make span-level comments easy to inspect and act on.
- Agent outputs should be traceable by run, model, and reasoning category.
- Final scoring should synthesize multiple signals instead of relying on a single heuristic.

## Open Questions

- How much of the online similarity search should be cached?
- Which signals should affect the final reading-worthiness score most strongly?
- How assertive should the AI-generation classifier be in user-facing language?
