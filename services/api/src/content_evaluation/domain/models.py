"""Domain models for content evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class SourceType(StrEnum):
    """Enumerate supported source types."""

    URL = "url"
    TEXT = "text"
    FILE = "file"
    ARTIFACT = "artifact"


class RunStatus(StrEnum):
    """Enumerate artifact lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RuntimeMode(StrEnum):
    """Enumerate runtime execution modes."""

    MOCK = "mock"
    LIVE = "live"


class OrchestratorBackend(StrEnum):
    """Enumerate orchestration engines."""

    LEGACY = "legacy"
    LANGGRAPH = "langgraph"


class AnalysisProviderFamily(StrEnum):
    """Enumerate supported LLM provider families."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MOCK = "mock"


class PersistenceMode(StrEnum):
    """Enumerate persistence strategies."""

    SESSION = "session"
    WORKSPACE = "workspace"


class RunJobStatus(StrEnum):
    """Enumerate durable worker job states."""

    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class AuthorType(StrEnum):
    """Enumerate comment author types."""

    AGENT = "agent"
    HUMAN = "human"


class ReviewState(StrEnum):
    """Enumerate agent review states."""

    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class AgentCategory(StrEnum):
    """Enumerate analysis categories."""

    SIMILARITY = "similarity"
    AI_LIKELIHOOD = "ai_likelihood"
    VALUE = "value"
    AUDIENCE = "audience"
    EDITORIAL = "editorial"
    SYNTHESIS = "synthesis"
    HUMAN = "human"


class ProviderKind(StrEnum):
    """Enumerate provider categories."""

    SEARCH = "search"
    ANALYSIS = "analysis"
    EXTRACT = "extract"


class AgentExecutionMode(StrEnum):
    """Enumerate agent execution styles."""

    SINGLE_TURN = "single_turn"
    MULTI_STEP = "multi_step"


class AgentPlanStatus(StrEnum):
    """Enumerate agent plan item states."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventType(StrEnum):
    """Enumerate live event categories."""

    RUN = "run"
    ARTIFACT = "artifact"
    AGENT = "agent"


class ArtifactSource(BaseModel):
    """Store source metadata for an artifact."""

    source_type: SourceType
    source_label: str
    title: str | None = None
    url: str | None = None
    imported: bool = False


class ArtifactBlock(BaseModel):
    """Store one normalized text block."""

    id: str = Field(default_factory=lambda: f"block-{uuid4()}")
    index: int
    text: str


class ArtifactDocument(BaseModel):
    """Store normalized reviewable content."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    source_type: SourceType
    source_label: str
    text: str
    blocks: list[ArtifactBlock]


class ArtifactAnchor(BaseModel):
    """Store a text-range anchor within one block."""

    id: str = Field(default_factory=lambda: f"anchor-{uuid4()}")
    block_id: str
    start_offset: int
    end_offset: int
    quote: str


class ArtifactReply(BaseModel):
    """Store one reply beneath a top-level comment."""

    id: str = Field(default_factory=lambda: f"reply-{uuid4()}")
    comment_id: str
    author_type: AuthorType
    author_label: str
    body: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ArtifactComment(BaseModel):
    """Store one top-level comment tied to an anchor."""

    id: str = Field(default_factory=lambda: f"comment-{uuid4()}")
    artifact_id: UUID
    anchor_id: str
    author_type: AuthorType
    author_label: str
    category: AgentCategory
    body: str
    suggestion: str | None = None
    review_state: ReviewState = ReviewState.UNREVIEWED
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    replies: list[ArtifactReply] = Field(default_factory=list)


class ArtifactThread(BaseModel):
    """Store the comments for a single anchor."""

    anchor: ArtifactAnchor
    comments: list[ArtifactComment]


class AgentFinding(BaseModel):
    """Store one structured agent finding."""

    id: str = Field(default_factory=lambda: f"finding-{uuid4()}")
    category: AgentCategory
    agent_name: str
    anchor_ids: list[str]
    rationale: str
    confidence: float
    model_name: str
    suggestion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactAgentPlanItem(BaseModel):
    """Store planned execution data for one agent."""

    agent_id: str
    display_name: str
    category: AgentCategory
    depends_on: list[str] = Field(default_factory=list)
    provider_kind: ProviderKind
    execution_mode: AgentExecutionMode
    instruction_file: str
    status: AgentPlanStatus = AgentPlanStatus.PENDING
    model_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None


class ArtifactAgentResult(BaseModel):
    """Store one resolved agent result."""

    agent_id: str
    category: AgentCategory
    status: AgentPlanStatus
    findings: list[AgentFinding] = Field(default_factory=list)
    summary: str | None = None
    raw_output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactSummary(BaseModel):
    """Store aggregate scores and narrative summary."""

    overall_score: int
    verdict: str
    value_summary: str
    audience_summary: str
    novelty_score: float
    ai_likelihood: float


class ArtifactEvent(BaseModel):
    """Store one durable artifact event."""

    id: str = Field(default_factory=lambda: f"event-{uuid4()}")
    artifact_id: UUID
    event_type: EventType
    stage: str
    message: str
    status: str
    progress: float | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    model_name: str | None = None
    snapshot_available: bool = False
    created_at: datetime = Field(default_factory=now_utc)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactDebug(BaseModel):
    """Store optional verbose debug trace data."""

    traces: list[dict[str, Any]] = Field(default_factory=list)


class ProviderRoute(BaseModel):
    """Store provider routing settings for one agent execution."""

    family: AnalysisProviderFamily
    model_name: str
    temperature: float = 0.0
    timeout_seconds: float = 45.0
    max_retries: int = 3
    streaming: bool = False


class RunConfig(BaseModel):
    """Store run configuration that shapes artifact creation."""

    selected_agents: list[str]
    resolved_agents: list[str] = Field(default_factory=list)
    runtime_mode: RuntimeMode
    orchestrator_backend: OrchestratorBackend = OrchestratorBackend.LANGGRAPH
    persistence_mode: PersistenceMode = PersistenceMode.SESSION
    include_debug_trace: bool = False


class AnalysisArtifact(BaseModel):
    """Store the complete artifact consumed by the UI and exports."""

    schema_version: str = "1.0"
    artifact_id: UUID = Field(default_factory=uuid4)
    status: RunStatus = RunStatus.QUEUED
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    source: ArtifactSource
    document: ArtifactDocument | None = None
    run_config: RunConfig
    agent_plan: list[ArtifactAgentPlanItem] = Field(default_factory=list)
    agent_results: list[ArtifactAgentResult] = Field(default_factory=list)
    anchors: list[ArtifactAnchor] = Field(default_factory=list)
    threads: list[ArtifactThread] = Field(default_factory=list)
    summary: ArtifactSummary | None = None
    events: list[ArtifactEvent] = Field(default_factory=list)
    debug: ArtifactDebug | None = None
    error_message: str | None = None


class RunInput(BaseModel):
    """Store one input request for a run."""

    source_type: SourceType
    source_label: str
    text: str | None = None
    title: str | None = None
    url: str | None = None
    selected_agents: list[str] = Field(default_factory=list)
    persistence_mode: PersistenceMode = PersistenceMode.SESSION
    include_debug_trace: bool = False


class RunJob(BaseModel):
    """Store one durable queued job for the worker."""

    artifact_id: UUID
    input_data: RunInput
    status: RunJobStatus = RunJobStatus.QUEUED
    attempts: int = 0
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class GraphNodeResult(BaseModel):
    """Store one node-level execution result used by graph checkpoints."""

    node_id: str
    agent_id: str | None = None
    status: str
    summary: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphRunState(BaseModel):
    """Store the resumable internal graph state for one artifact run."""

    artifact_id: UUID
    input_data: RunInput
    selected_agents: list[str] = Field(default_factory=list)
    resolved_agents: list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    completed_agents: list[str] = Field(default_factory=list)
    extracted_text: str | None = None
    extracted_title: str | None = None
    node_results: list[GraphNodeResult] = Field(default_factory=list)
    error_message: str | None = None
    checkpoint_version: int = 0
    last_updated_at: datetime = Field(default_factory=now_utc)


class GraphCheckpoint(BaseModel):
    """Store the most recent durable graph checkpoint for one artifact."""

    artifact_id: UUID
    state: GraphRunState
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class AgentCatalogEntry(BaseModel):
    """Expose one agent definition over the API."""

    agent_id: str
    display_name: str
    category: AgentCategory
    depends_on: list[str]
    execution_mode: AgentExecutionMode
    provider_kind: ProviderKind
    description: str
    default_enabled: bool = True
    preferred_provider_family: AnalysisProviderFamily | None = None
    preferred_model_name: str | None = None


class ReadinessReport(BaseModel):
    """Store readiness information for health endpoints."""

    status: str
    app_env: str
    processing_mode: RuntimeMode
    persistent_storage: bool
    database_ready: bool
    providers_ready: bool
    orchestrator_backend: OrchestratorBackend
