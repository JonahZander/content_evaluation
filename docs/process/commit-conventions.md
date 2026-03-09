# Commit Conventions

Use a consistent message shape for every commit:

`<type>(<scope>): <summary>`

## Allowed Types

- `docs`
- `feat`
- `fix`
- `refactor`
- `test`
- `chore`

## Scope Guidance

Use a short scope that points to the primary area changed, for example:

- `docs`
- `agents`
- `frontend`
- `backend`
- `review`
- `observability`
- `repo`

## Body Template

Use the commit body to capture:

- Why this change exists
- What changed
- How it was checked

Example:

```text
docs(repo): scaffold agent-first documentation

Why:
- establish the system-of-record docs structure

What:
- add AGENTS.md and docs indices
- add a repo-local commit skill and git message template

Checks:
- reviewed links and repo structure locally
```
