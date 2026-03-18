"""Domain models for content evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def now_utc() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class SourceType(StrEnum):
    """Enumerate supported source types."""

    URL = "url"
    TEXT = "text"
    FILE = "file"
    ARTIFACT = "artifact"


class ContentFormat(StrEnum):
    """Enumerate stored content formats."""

    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"


class RunStatus(StrEnum):
    """Enumerate artifact lifecycle states."""

    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


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
    CANCELED = "canceled"


class RunMode(StrEnum):
    """Enumerate queued run behaviors."""

    CREATE = "create"
    APPEND_AGENTS = "append_agents"


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

    FACT_CHECK = "fact_check"
    SIMILARITY = "similarity"
    AI_LIKELIHOOD = "ai_likelihood"
    VALUE = "value"
    AUDIENCE = "audience"
    EDITORIAL = "editorial"
    SYNTHESIS = "synthesis"
    HUMAN = "human"


class ProviderKind(StrEnum):
    """Enumerate provider categories."""

    DEEP_RESEARCH = "deep_research"
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


class ArtifactBlockKind(StrEnum):
    """Enumerate supported rendered document block kinds."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    CODE = "code"


class ArtifactBlockOrigin(StrEnum):
    """Enumerate where one rendered block came from."""

    SOURCE = "source"
    SYNTHETIC_UNMATCHED = "synthetic_unmatched"


class ArtifactAnchorMatchKind(StrEnum):
    """Enumerate whether one anchor resolves to source or fallback content."""

    SOURCE = "source"
    SYNTHETIC_UNMATCHED = "synthetic_unmatched"


class ArtifactInlineMarkKind(StrEnum):
    """Enumerate supported inline markdown marks."""

    STRONG = "strong"
    EMPHASIS = "emphasis"
    CODE = "code"
    LINK = "link"


class ArtifactInlineMark(BaseModel):
    """Store one inline formatting span within a block."""

    start_offset: int
    end_offset: int
    kind: ArtifactInlineMarkKind
    href: str | None = None


class ArtifactBlock(BaseModel):
    """Store one normalized text block."""

    id: str = Field(default_factory=lambda: f"block-{uuid4()}")
    index: int
    text: str
    kind: ArtifactBlockKind = ArtifactBlockKind.PARAGRAPH
    origin: ArtifactBlockOrigin = ArtifactBlockOrigin.SOURCE
    markdown: str | None = None
    level: int | None = None
    language: str | None = None
    marks: list[ArtifactInlineMark] = Field(default_factory=list)


class ArtifactDocument(BaseModel):
    """Store normalized reviewable content."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    source_type: SourceType
    source_label: str
    content_format: ContentFormat = ContentFormat.PLAIN_TEXT
    raw_content: str = ""
    text: str
    blocks: list[ArtifactBlock]


class ExtractedContent(BaseModel):
    """Store one extracted source payload before normalization."""

    title: str
    content: str
    content_format: ContentFormat = ContentFormat.PLAIN_TEXT
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactAnchor(BaseModel):
    """Store a text-range anchor across one or more contiguous blocks."""

    id: str = Field(default_factory=lambda: f"anchor-{uuid4()}")
    block_id: str = ""
    start_offset: int = 0
    end_offset: int = 0
    quote: str
    match_kind: ArtifactAnchorMatchKind = ArtifactAnchorMatchKind.SOURCE
    segments: list["ArtifactAnchorSegment"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_legacy_fields(self) -> ArtifactAnchor:
        """Keep legacy single-block fields aligned with canonical segments."""

        if not self.segments:
            self.segments = [
                ArtifactAnchorSegment(
                    block_id=self.block_id,
                    start_offset=self.start_offset,
                    end_offset=self.end_offset,
                )
            ]
        first_segment = self.segments[0]
        self.block_id = first_segment.block_id
        self.start_offset = first_segment.start_offset
        self.end_offset = first_segment.end_offset
        return self


class ArtifactAnchorSegment(BaseModel):
    """Store one block-local slice for a multi-block anchor."""

    block_id: str
    start_offset: int
    end_offset: int


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
    sources: list[str] = Field(default_factory=list)
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
    sources: list[str] = Field(default_factory=list)
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


class ArtifactOverlapItem(BaseModel):
    """Store one overlapping article surfaced for the review summary."""

    title: str
    url: str
    note: str


class ArtifactReviewSummary(BaseModel):
    """Store the narrative summary content shown above the document."""

    content_summary: str
    research_summary: str
    inferred_audience: str
    overlap_items: list[ArtifactOverlapItem] = Field(default_factory=list)


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
    attempt: int | None = None
    max_attempts: int | None = None
    error_kind: str | None = None
    provider_name: str | None = None
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

    schema_version: str = "1.2"
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
    review_summary: ArtifactReviewSummary | None = None
    events: list[ArtifactEvent] = Field(default_factory=list)
    debug: ArtifactDebug | None = None
    error_message: str | None = None


class RunInput(BaseModel):
    """Store one input request for a run."""

    mode: RunMode = RunMode.CREATE
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
    extracted_content: str | None = None
    extracted_title: str | None = None
    extracted_content_format: ContentFormat = ContentFormat.PLAIN_TEXT
    extracted_metadata: dict[str, Any] = Field(default_factory=dict)
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
