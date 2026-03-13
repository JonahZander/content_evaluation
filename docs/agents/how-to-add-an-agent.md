# How to Add a New Agent

This guide covers the concrete steps for adding a new specialist agent to the content evaluation pipeline.

## Overview

Adding an agent requires changes in these locations:
1. A new instruction file under `agents/instructions/`
2. A `result_schema` Pydantic model (or reuse `FindingPayload`)
3. A registry entry in `agents/registry.py`
4. A LangGraph node in `services/orchestration.py`
5. A result-assembly step in the artifact builder
6. A category color in `category-colors.ts`
7. A test for the agent result schema
8. A doc update in `multi-agent-workflow.md`

## Step 1: Write the instruction file

Create a markdown file at:

```
services/api/src/content_evaluation/agents/instructions/<agent_id>.md
```

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
- `depends_on=("similarity", "value")` means this agent waits for those agents first.
- `synthesis` already depends on all current specialist agents; update its `depends_on` if your agent should feed into the synthesis score.

## Step 4: Add the LangGraph node

In `services/api/src/content_evaluation/services/orchestration.py`, add a node to the LangGraph graph for the new agent. Follow the pattern of existing single-turn or multi-step nodes. The node receives `GraphRunState` and should:

1. Call `self._run_analysis_agent(agent_id, state)` for analysis agents.
2. Emit progress events before and after execution.
3. Record the result in `state["node_results"]`.

Register the node in `_build_graph()` using `graph.add_node(agent_id, node_function)` and add edges based on `depends_on`.

## Step 5: Add the result-assembly step

In the artifact builder section of `orchestration.py`, add handling for the new agent's output in `_assemble_artifact()`. This converts the raw node result into:
- `ArtifactAgentResult` entries
- `ArtifactAnchor` + `ArtifactThread` entries for each finding
- Summary contributions if applicable

## Step 6: Add the category color

In `apps/web/src/components/review/category-colors.ts`, add a color for the new `AgentCategory` value if you added one. If reusing an existing category like `editorial`, no change is needed.

## Step 7: Write a schema test

Add a test to `services/api/tests/` that verifies the agent's result schema can be instantiated and validates correctly. Example:

```python
def test_my_agent_result_schema():
    payload = FindingPayload(
        excerpt="exact source text",
        rationale="why this is notable",
        confidence=0.85,
    )
    assert payload.confidence == 0.85
```

## Step 8: Update multi-agent-workflow.md

Add the new agent to the "Current Agent Roles" section in `docs/agents/multi-agent-workflow.md`. Describe:
- What it analyzes
- Whether it is single-turn or multi-step
- Any dependencies on other agents

## Quick Checklist

- [ ] `agents/instructions/<agent_id>.md` created
- [ ] Result schema defined (or `FindingPayload` reused)
- [ ] `AgentDefinition` added to `_AGENTS` in `registry.py`
- [ ] LangGraph node added to `orchestration.py`
- [ ] Result-assembly step added to artifact builder
- [ ] Category color added to `category-colors.ts` (if new category)
- [ ] Schema test written
- [ ] `multi-agent-workflow.md` updated
