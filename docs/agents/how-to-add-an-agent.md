# How to Add a New Agent

This guide covers the concrete steps for adding a new specialist agent to the content evaluation pipeline.

## Overview

Adding an agent requires changes in these locations:
1. An instruction file under `agents/instructions/`
2. A `result_schema` Pydantic model (or reuse `FindingPayload`)
3. A registry entry in `agents/registry.py`
4. Optional orchestration changes if the agent needs a new execution path or custom artifact handling
5. Frontend category/type updates if you add a new category
6. Tests for the registry, schema, and any custom behavior
7. A doc update in `multi-agent-workflow.md`

## Step 1: Write the instruction file

Create a markdown file somewhere under:

```
services/api/src/content_evaluation/agents/instructions/
```

The registry entry's `instruction_file` should point to that relative path. Most agents use a flat file like `editorial.md`; nested paths like `fact_check/research_brief.md` also work.

Write the analysis prompt. Follow the patterns in the existing instruction files:
- State the agent's job in one sentence.
- Explain what to look for and how to structure findings.
- Require exact word-for-word quotes from the source text (no paraphrasing).
- Use ellipses only for real content omissions, not summarization.
- Split evidence that would span more than 3 paragraphs into separate findings.

## Step 2: Define a result schema (if needed)

Most agents use `FindingPayload` from `agents/registry.py`:

```python
class FindingPayload(BaseModel):
    excerpt: str
    rationale: str
    confidence: float
    suggestion: str | None = None
```

If your agent produces a different shape, add a new Pydantic model to `domain/models.py` following the existing naming pattern (`<AgentName>Result`). Keep schemas minimal — only fields the UI or downstream agents will actually use.

## Step 3: Add the registry entry

In `services/api/src/content_evaluation/agents/registry.py`, add an `AgentDefinition` to the `_AGENTS` tuple:

```python
AgentDefinition(
    agent_id="my_agent",
    display_name="My Agent",
    description="One-sentence description shown in the UI agent picker.",
    category=AgentCategory.EDITORIAL,  # pick the right category
    depends_on=(),                      # tuple of agent_ids this agent needs
    provider_kind=ProviderKind.ANALYSIS,
    execution_mode=AgentExecutionMode.SINGLE_TURN,
    instruction_file="my_agent.md",
    result_schema=FindingPayload,
    default_enabled=True,
)
```

**Dependency notes:**
- `depends_on=()` means the agent runs in parallel with other independent agents.
- `depends_on=("fact_check", "ai_likelihood")` means this agent waits for those agents first.
- New run planning currently schedules `fact_check`, `ai_likelihood`, and `editorial` for the main flow. If your new agent should participate there, update the dependency graph and current-workflow docs together.

## Step 4: Verify whether orchestration changes are actually needed

Most new agents do not need a manually registered LangGraph node. The current graph is built from the registry in `services/orchestration.py`, and dependencies from `depends_on` are wired automatically.

You only need orchestration changes when the new agent:
- uses a new `provider_kind` or `execution_mode`
- needs custom upstream context beyond the standard dependency payload
- needs special artifact assembly behavior beyond the default finding-to-thread flow

If the agent fits the existing analysis/deep-research patterns, the registry entry is enough for graph planning and execution.

## Step 5: Verify whether custom artifact assembly is needed

The default artifact builder already converts generic finding payloads into:
- `ArtifactAgentResult` entries
- `ArtifactAnchor` records
- `ArtifactThread` comment-rail items for agents that should create threads

Add custom assembly logic only if the agent needs summary-only behavior, special metadata shaping, or UI-specific surfaces like the current fact-check evidence and audience summary flows.

## Step 6: Add frontend category updates if needed

If you add a new `AgentCategory` value, update:
- `apps/web/src/lib/types.ts`
- `apps/web/src/components/review/category-colors.ts`

If the agent reuses an existing category like `editorial`, no frontend category changes are needed.

## Step 7: Write tests

At minimum, add a backend test that verifies the registry entry and result schema behave as expected. If you added custom orchestration or assembly behavior, cover that too. Example:

```python
def test_my_agent_result_schema():
    payload = FindingPayload(
        excerpt="exact source text",
        rationale="why this is notable",
        confidence=0.85,
    )
    assert payload.confidence == 0.85
```

Also add or extend a registry/dependency test when the new agent changes execution order.

## Step 8: Update multi-agent-workflow.md

Add the new agent to the "Current Agent Roles" section in `docs/agents/multi-agent-workflow.md`. Describe:
- What it analyzes
- Whether it is single-turn or multi-step
- Any dependencies on other agents

## Quick Checklist

- [ ] Instruction file created under `agents/instructions/`
- [ ] Result schema defined (or `FindingPayload` reused)
- [ ] `AgentDefinition` added to `_AGENTS` in `registry.py`
- [ ] Orchestration updated only if the agent needs a new execution path or custom context
- [ ] Artifact assembly updated only if the default finding flow is not enough
- [ ] Frontend category/type updates made if a new category was introduced
- [ ] Tests added for schema, registry, and any custom behavior
- [ ] `multi-agent-workflow.md` updated
