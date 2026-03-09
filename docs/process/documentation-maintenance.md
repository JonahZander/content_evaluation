# Documentation Maintenance

## Principle

Repository documentation is part of the product surface for coding agents.

## Rules

1. Update relevant markdown in the same change that alters behavior or expectations.
2. Keep `AGENTS.md` short and stable; push detailed knowledge into `docs/`.
3. Add new docs to the nearest section index so they are discoverable.
4. Do not duplicate the same rule across many files without a clear reason.
5. Prefer narrow documents by domain instead of one large repository manual.

## When Feedback Arrives

When user or reviewer feedback changes scope, behavior, naming, or workflow:

- update the affected source-of-truth markdown
- update cross-links if discoverability changed
- avoid editing unrelated docs

## Progressive Disclosure Standard

- Frontend changes should normally update frontend docs only.
- Backend pipeline changes should normally update backend or agent docs.
- Cross-cutting changes should update the minimal set of affected documents.
