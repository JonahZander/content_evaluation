---
name: commit-style
description: Use this skill when creating a git commit in this repository and you need the project-standard commit message template and scope conventions.
---

# Commit Style

Use this skill whenever you are preparing a git commit for this repository.

## Goal

Keep commit messages consistent, short, and easy for humans and agents to scan.

## Required Format

Use this subject line format:

`<type>(<scope>): <summary>`

Allowed types:

- `docs`
- `feat`
- `fix`
- `refactor`
- `test`
- `chore`

Common scopes:

- `docs`
- `agents`
- `frontend`
- `backend`
- `review`
- `observability`
- `repo`

## Body Template

Use this exact section order when a body is needed:

```text
Why:
- ...

What:
- ...

Checks:
- ...
```

## Workflow

1. Read `docs/process/commit-conventions.md` if the scope is unclear.
2. Draft the subject line with one primary scope.
3. Add the body when the change is not trivially obvious.
4. Mention doc updates in the `What:` section when they are part of the same change.

## Do Not

- Do not use vague summaries like `update stuff`.
- Do not combine multiple unrelated scopes in one commit.
- Do not skip documentation changes from the message when docs were part of the change.
