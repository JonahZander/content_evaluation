"""Declarative agent registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from content_evaluation.domain.models import (
    AgentCatalogEntry,
    AgentCategory,
    AgentExecutionMode,
    ProviderKind,
    ProviderRoute,
)


class FindingPayload(BaseModel):
    """Validate one generic finding payload."""

    excerpt: str
    rationale: str
    confidence: float
    suggestion: str | None = None
    sources: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Describe one analysis agent."""

    agent_id: str
    display_name: str
    description: str
    category: AgentCategory
    depends_on: tuple[str, ...]
    provider_kind: ProviderKind
    execution_mode: AgentExecutionMode
    instruction_file: str
    result_schema: type[BaseModel]
    default_enabled: bool = True
    preferred_route: ProviderRoute | None = None

    def instruction_path(self) -> Path:
        """Return the absolute instruction path."""

        return Path(__file__).with_name("instructions") / self.instruction_file

    def to_catalog_entry(self) -> AgentCatalogEntry:
        """Convert to the API-safe catalog type."""

        return AgentCatalogEntry(
            agent_id=self.agent_id,
            display_name=self.display_name,
            description=self.description,
            category=self.category,
            depends_on=list(self.depends_on),
            execution_mode=self.execution_mode,
            provider_kind=self.provider_kind,
            default_enabled=self.default_enabled,
            preferred_provider_family=(
                self.preferred_route.family if self.preferred_route is not None else None
            ),
            preferred_model_name=(
                self.preferred_route.model_name if self.preferred_route is not None else None
            ),
        )


_AGENTS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        agent_id="similarity",
        display_name="Similarity Research",
        description="Looks for similar public posts and framing overlap.",
        category=AgentCategory.SIMILARITY,
        depends_on=(),
        provider_kind=ProviderKind.SEARCH,
        execution_mode=AgentExecutionMode.MULTI_STEP,
        instruction_file="similarity.md",
        result_schema=FindingPayload,
    ),
    AgentDefinition(
        agent_id="ai_likelihood",
        display_name="AI Likelihood",
        description="Estimates whether the writing appears AI-generated.",
        category=AgentCategory.AI_LIKELIHOOD,
        depends_on=(),
        provider_kind=ProviderKind.ANALYSIS,
        execution_mode=AgentExecutionMode.SINGLE_TURN,
        instruction_file="ai_likelihood.md",
        result_schema=FindingPayload,
    ),
    AgentDefinition(
        agent_id="value",
        display_name="Value Analysis",
        description="Finds the strongest value proposition in the text.",
        category=AgentCategory.VALUE,
        depends_on=(),
        provider_kind=ProviderKind.ANALYSIS,
        execution_mode=AgentExecutionMode.SINGLE_TURN,
        instruction_file="value.md",
        result_schema=FindingPayload,
    ),
    AgentDefinition(
        agent_id="audience",
        display_name="Audience Analysis",
        description="Infers the most likely target audience.",
        category=AgentCategory.AUDIENCE,
        depends_on=(),
        provider_kind=ProviderKind.ANALYSIS,
        execution_mode=AgentExecutionMode.SINGLE_TURN,
        instruction_file="audience.md",
        result_schema=FindingPayload,
    ),
    AgentDefinition(
        agent_id="editorial",
        display_name="Editorial Recommendations",
        description="Creates span-level editorial suggestions.",
        category=AgentCategory.EDITORIAL,
        depends_on=(),
        provider_kind=ProviderKind.ANALYSIS,
        execution_mode=AgentExecutionMode.SINGLE_TURN,
        instruction_file="editorial.md",
        result_schema=FindingPayload,
    ),
    AgentDefinition(
        agent_id="fact_check",
        display_name="Fact Check",
        description="Verifies key claims against live web sources and flags overlapping existing content.",
        category=AgentCategory.FACT_CHECK,
        depends_on=(),
        provider_kind=ProviderKind.DEEP_RESEARCH,
        execution_mode=AgentExecutionMode.MULTI_STEP,
        instruction_file="fact_check/research_brief.md",
        result_schema=FindingPayload,
        default_enabled=False,
    ),
    AgentDefinition(
        agent_id="synthesis",
        display_name="Synthesis and Scoring",
        description="Produces a final verdict after upstream agents finish.",
        category=AgentCategory.SYNTHESIS,
        depends_on=("similarity", "ai_likelihood", "value", "audience", "editorial"),
        provider_kind=ProviderKind.ANALYSIS,
        execution_mode=AgentExecutionMode.SINGLE_TURN,
        instruction_file="synthesis.md",
        result_schema=FindingPayload,
    ),
)


def list_agent_definitions() -> list[AgentDefinition]:
    """Return all configured agents."""

    return list(_AGENTS)


def agent_catalog() -> list[AgentCatalogEntry]:
    """Return API-safe catalog entries."""

    return [agent.to_catalog_entry() for agent in _AGENTS]


def get_agent_definition(agent_id: str) -> AgentDefinition:
    """Return one agent definition or raise."""

    for agent in _AGENTS:
        if agent.agent_id == agent_id:
            return agent
    raise KeyError(agent_id)


def load_instruction_text(agent: AgentDefinition) -> str:
    """Return the instruction body for one agent."""

    return agent.instruction_path().read_text(encoding="utf-8").strip()
