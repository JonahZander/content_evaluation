---
name: implement-plan
description: Orchestrate a multi-step plan by delegating implementation and testing to subagents, committing each section incrementally. Use when the user points to a plan file and wants it executed end-to-end.
---

# Implement Plan

Use this skill when the user wants to execute a plan file end-to-end.
You are the **orchestrator** — you coordinate, delegate, and verify, but you do not write the implementation code yourself.

## Usage

```
/implement-plan <path-to-plan-file>
```

If no path is provided, check `docs/plans/active/` for an active plan and ask the user to confirm which one to execute.

## Before You Start

### 1. Understand the Plan

Read the plan file in full. Identify every discrete section or step. Map dependencies between sections — which sections must complete before others can begin.

### 2. Find Execution and Testing Instructions

Search the repository documentation for how to run, build, and test the project:

- Read `docs/operations/local-development.md` for common commands, dev workflow, and test commands
- Read `docs/operations/index.md` for any additional operational guidance
- Check for a root-level `Makefile`, `package.json` scripts section, or `pyproject.toml` scripts
- Check for CI configuration (`.github/workflows/`, `.gitlab-ci.yml`, etc.) that reveals the canonical test and lint commands

If you cannot find clear instructions for how to execute and test the code, **stop and ask the user**:
> "I could not find documentation on how to run and test this project. Please point me to the relevant docs or tell me the commands to use."

Do not guess test commands. Do not proceed without knowing how to verify your work.

### 3. Find Coding Standards

Search the repository for coding standards and conventions:

- Read `docs/process/index.md` and any linked style or convention docs
- Read `docs/process/commit-conventions.md` for commit message format
- Check for linter configs (`.eslintrc`, `ruff.toml`, `.prettierrc`, etc.) that encode style rules
- Check for `CONTRIBUTING.md` or similar guides
- Review a few existing files in the area being changed to absorb the local style

If you cannot find documented coding standards, **ask the user**:
> "I could not find documented coding standards for this project. Should I follow a specific style guide, or should I match the patterns in the existing code?"

## Implementation Cycle

Repeat this cycle for each section of the plan, in dependency order:

### Step 1 — Prepare the Task

- Identify the files, APIs, and dependencies involved in this section
- Write a precise, self-contained task description for the implementation subagent
- Include in the prompt:
  - The specific section of the plan being implemented (paste it in full)
  - All relevant file paths, function signatures, and data contracts
  - The coding standards discovered in the preparation phase
  - A clear definition of done with acceptance criteria
  - Instruction to match existing patterns and avoid over-engineering

### Step 2 — Implement via Subagent

Spawn an implementation subagent with the prepared task. The subagent prompt must include:

- The full context it needs (it has no memory of prior steps)
- The coding standards to follow
- Explicit instruction: no speculative abstractions, no dead code, no feature flags unless the plan calls for them, match existing codebase patterns

Wait for the subagent to complete and review its output before proceeding.

### Step 3 — Test via Subagent

Spawn a separate testing subagent that:

- Runs the test commands discovered during preparation (unit tests, integration tests, type checks, linting)
- Writes new tests for the implemented functionality if the plan calls for testable behavior and tests don't already exist
- Reports pass/fail status with full output for any failures

**If tests fail:**
1. Spawn a new implementation subagent with the failure output and ask it to fix the issues
2. Re-run the testing subagent
3. Repeat until tests pass
4. If a fix cycle repeats more than 3 times, stop and ask the user for guidance

Do not move to the commit step until all tests pass.

### Step 4 — Commit

Once the section passes testing:

- Stage only the files relevant to this section
- Write a commit message following the project's commit conventions (see `docs/process/commit-conventions.md` and the commit-style skill)
- Include any documentation updates in the same commit if the section changed behavior, APIs, or workflows
- Do not batch multiple plan sections into a single commit

## Rules

- **One section at a time.** Never implement multiple sections in parallel unless they are explicitly independent and have no shared files.
- **Never skip testing.** Every implemented section must pass tests before being committed.
- **Dependencies first.** If section B depends on section A, confirm A is committed and passing before starting B.
- **Ask, don't guess.** If the plan is ambiguous, a dependency is unclear, or you cannot find how to test something, stop and ask the user.
- **Self-contained subagent prompts.** Each subagent starts fresh with no memory. Include all context it needs in the prompt.
- **Incremental commits.** Each completed section gets its own commit. This keeps the history bisectable and reviewable.

## After All Sections Complete

1. Run the full test suite one final time to catch any cross-section regressions
2. Review the plan file — confirm every section has been addressed
3. If the plan is in `docs/plans/active/`, move it to `docs/plans/completed/`
4. Report a summary to the user: what was implemented, how many commits were made, and any decisions or deviations from the plan

## Do Not

- Do not write implementation code directly — always delegate to a subagent
- Do not proceed without knowing how to test the project
- Do not proceed without understanding the project's coding standards
- Do not combine unrelated sections in one commit
- Do not silently skip a failing test
- Do not make architectural decisions that the plan does not call for — escalate to the user instead
