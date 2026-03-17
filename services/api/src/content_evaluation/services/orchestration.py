"""Artifact orchestration service."""

from __future__ import annotations

import asyncio
import operator
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from content_evaluation.agents.registry import (
    AgentDefinition,
    FindingPayload,
    get_agent_definition,
    load_instruction_text,
)
from content_evaluation.domain.exceptions import NotFoundError, ProviderError, RunCancelledError, ValidationError
from content_evaluation.domain.models import (
    AgentCatalogEntry,
    AgentCategory,
    AgentExecutionMode,
    AgentFinding,
    AgentPlanStatus,
    AnalysisArtifact,
    ArtifactAgentPlanItem,
    ArtifactAgentResult,
    ArtifactAnchor,
    ArtifactAnchorMatchKind,
    ArtifactAnchorSegment,
    ArtifactBlock,
    ArtifactBlockKind,
    ArtifactBlockOrigin,
    ArtifactComment,
    ArtifactDocument,
    ArtifactDebug,
    ArtifactEvent,
    ContentFormat,
    ExtractedContent,
    ArtifactSource,
    ArtifactSummary,
    AuthorType,
    EventType,
    GraphCheckpoint,
    GraphNodeResult,
    GraphRunState,
    OrchestratorBackend,
    PersistenceMode,
    ProviderKind,
    ProviderRoute,
    ReviewState,
    RunConfig,
    RunInput,
    RunStatus,
    RuntimeMode,
    SourceType,
)
from content_evaluation.providers.interfaces.analysis import AnalysisProvider
from content_evaluation.providers.interfaces.deep_research import DeepResearchProvider
from content_evaluation.providers.interfaces.extraction import ContentExtractionProvider
from content_evaluation.providers.interfaces.search import SimilaritySearchProvider
from content_evaluation.repositories.base import RunRepository
from content_evaluation.services.anchors import create_anchor_from_excerpt, sanitize_excerpt
from content_evaluation.services.normalization import (
    build_fact_check_brief,
    build_similarity_query,
    normalize_text,
)


@dataclass(slots=True)
class AgentExecutionResult:
    """Hold one completed agent execution result."""

    definition: AgentDefinition
    raw_output: dict[str, object]
    findings: list[FindingPayload]
    summary: str | None
    metadata: dict[str, object]
    model_name: str
    usage: dict[str, int] | None = None


class LangGraphState(TypedDict):
    """Represent the internal LangGraph state for one artifact run."""

    artifact_id: UUID
    input_data: RunInput
    selected_agents: list[str]
    resolved_agents: list[str]
    extracted_content: str | None
    extracted_title: str | None
    extracted_content_format: ContentFormat
    extracted_metadata: dict[str, object]
    completed_nodes: Annotated[list[str], operator.add]
    completed_agents: Annotated[list[str], operator.add]
    node_results: Annotated[list[dict[str, object]], operator.add]
    error_messages: Annotated[list[str], operator.add]


class RunOrchestrator:
    """Create artifacts and orchestrate all analysis steps."""

    def __init__(
        self,
        repository: RunRepository,
        analysis_provider: AnalysisProvider,
        search_provider: SimilaritySearchProvider,
        extraction_provider: ContentExtractionProvider,
        runtime_mode: RuntimeMode,
        persistent_storage_enabled: bool,
        orchestrator_backend: OrchestratorBackend,
        agent_max_retries: int = 2,
        deep_research_provider: DeepResearchProvider | None = None,
    ) -> None:
        """Initialize the orchestrator."""

        self._repository = repository
        self._analysis_provider = analysis_provider
        self._search_provider = search_provider
        self._extraction_provider = extraction_provider
        self._runtime_mode = runtime_mode
        self._persistent_storage_enabled = persistent_storage_enabled
        self._orchestrator_backend = orchestrator_backend
        self._agent_max_retries = agent_max_retries
        self._deep_research_provider = deep_research_provider
        self._artifact_locks: dict[UUID, asyncio.Lock] = {}

    def list_agents(self) -> list[AgentCatalogEntry]:
        """Return the public agent catalog."""

        from content_evaluation.agents.registry import agent_catalog

        return agent_catalog()

    async def create_run(self, input_data: RunInput) -> AnalysisArtifact:
        """Create one queued artifact."""

        persistence_mode = self._resolve_persistence_mode(input_data.persistence_mode)
        resolved_agent_ids = _expand_agent_ids(input_data.selected_agents)
        artifact = AnalysisArtifact(
            source=ArtifactSource(
                source_type=input_data.source_type,
                source_label=input_data.source_label,
                title=input_data.title,
                url=input_data.url,
            ),
            run_config=RunConfig(
                selected_agents=input_data.selected_agents or _default_agent_ids(),
                resolved_agents=resolved_agent_ids,
                runtime_mode=self._runtime_mode,
                orchestrator_backend=self._orchestrator_backend,
                persistence_mode=persistence_mode,
                include_debug_trace=input_data.include_debug_trace,
            ),
            agent_plan=[
                ArtifactAgentPlanItem(
                    agent_id=definition.agent_id,
                    display_name=definition.display_name,
                    category=definition.category,
                    depends_on=list(definition.depends_on),
                    provider_kind=definition.provider_kind,
                    execution_mode=definition.execution_mode,
                    instruction_file=str(definition.instruction_path().name),
                )
                for definition in _plan_order(resolved_agent_ids)
            ],
            debug=ArtifactDebug() if input_data.include_debug_trace else None,
        )
        artifact.events.append(
            ArtifactEvent(
                artifact_id=artifact.artifact_id,
                event_type=EventType.RUN,
                stage="run",
                status="queued",
                message="Run queued",
                progress=0.0,
                attempt=1,
                max_attempts=1,
            )
        )
        return await self._repository.create_artifact(artifact)

    async def import_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist one imported artifact."""

        artifact.source.imported = True
        artifact.run_config.persistence_mode = self._resolve_persistence_mode(artifact.run_config.persistence_mode)
        existing = await self._repository.get_artifact(artifact.artifact_id)
        if existing is None:
            return await self._repository.create_artifact(artifact)
        return await self._repository.update_artifact(artifact)

    async def preview_source_document(self, input_data: RunInput) -> ArtifactDocument:
        """Resolve and normalize one source without queueing a run."""

        extracted = await self._resolve_source(input_data)
        return normalize_text(
            input_data,
            extracted.content,
            extracted.title,
            content_format=extracted.content_format,
        )

    async def cancel_run(self, artifact_id: UUID) -> AnalysisArtifact:
        """Cancel one queued or running run."""

        artifact = await self._require_artifact(artifact_id)
        if artifact.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
            return artifact

        artifact.status = RunStatus.CANCELED
        artifact.error_message = "Run stopped by user"
        for item in artifact.agent_plan:
            if item.status in {AgentPlanStatus.PENDING, AgentPlanStatus.QUEUED, AgentPlanStatus.RUNNING}:
                item.status = AgentPlanStatus.SKIPPED
                item.message = "Run stopped by user"
        await self._append_event(
            artifact,
            EventType.RUN,
            "run",
            "canceled",
            "Run stopped by user",
            progress=1.0,
            snapshot_available=True,
        )
        await self._repository.cancel_run_job(artifact_id)
        self._artifact_locks.pop(artifact_id, None)
        return artifact

    async def process_run(
        self,
        artifact_id: UUID,
        input_data: RunInput,
        *,
        attempt: int = 1,
        max_attempts: int | None = None,
    ) -> None:
        """Process one queued artifact."""

        try:
            if self._orchestrator_backend is OrchestratorBackend.LANGGRAPH:
                await self._process_run_with_langgraph(
                    artifact_id, input_data, attempt=attempt, max_attempts=max_attempts
                )
                return
            await self._process_run_legacy(artifact_id, input_data, attempt=attempt, max_attempts=max_attempts)
        finally:
            self._artifact_locks.pop(artifact_id, None)

    async def _process_run_legacy(
        self,
        artifact_id: UUID,
        input_data: RunInput,
        *,
        attempt: int,
        max_attempts: int | None,
    ) -> None:
        """Process one queued artifact through the legacy loop."""

        artifact = await self._require_artifact(artifact_id)
        artifact.status = RunStatus.RUNNING
        artifact.error_message = None
        if attempt > 1:
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "resumed",
                "Run resumed after worker retry",
                progress=_progress_for_artifact(artifact),
                snapshot_available=True,
                attempt=attempt,
                max_attempts=max_attempts,
            )
        await self._append_event(
            artifact,
            EventType.RUN,
            "run",
            "started",
            "Run started",
            snapshot_available=True,
            attempt=attempt,
            max_attempts=max_attempts,
        )

        try:
            await self._ensure_run_active(artifact_id)
            extracted = await self._resolve_source(input_data)
            await self._append_event(
                artifact,
                EventType.ARTIFACT,
                "extraction",
                "completed",
                _source_message(extracted),
                progress=0.02,
                snapshot_available=True,
                metadata=extracted.metadata,
            )
            await self._ensure_run_active(artifact_id)
            artifact.document = normalize_text(
                input_data,
                extracted.content,
                extracted.title,
                content_format=extracted.content_format,
            )
            artifact.source.title = artifact.document.title
            await self._append_event(
                artifact,
                EventType.ARTIFACT,
                "normalization",
                "completed",
                "Document normalized",
                progress=0.05,
                snapshot_available=True,
            )

            for batch in _execution_batches(artifact.run_config.resolved_agents):
                await self._ensure_run_active(artifact_id)
                await self._queue_batch(artifact, batch)
                await self._run_batch(artifact, batch)

            await self._ensure_run_active(artifact_id)
            artifact.summary = _build_summary(artifact)
            artifact.status = RunStatus.COMPLETED
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "completed",
                "Run completed",
                progress=1.0,
                snapshot_available=True,
            )
        except RunCancelledError:
            artifact = await self._require_artifact(artifact_id)
            artifact.status = RunStatus.CANCELED
            await self._repository.update_artifact(artifact)
        except Exception as error:
            artifact.status = RunStatus.FAILED
            artifact.error_message = str(error)
            error_kind = error.kind if isinstance(error, ProviderError) else None
            provider_name = error.provider_name if isinstance(error, ProviderError) else None
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "failed",
                str(error),
                progress=1.0,
                error_kind=error_kind,
                provider_name=provider_name,
                snapshot_available=True,
            )
            raise

    async def _process_run_with_langgraph(
        self,
        artifact_id: UUID,
        input_data: RunInput,
        *,
        attempt: int,
        max_attempts: int | None,
    ) -> None:
        """Process one queued artifact through LangGraph."""

        artifact = await self._require_artifact(artifact_id)
        artifact.status = RunStatus.RUNNING
        artifact.error_message = None
        checkpoint = await self._repository.get_graph_checkpoint(artifact_id)
        if attempt > 1 or checkpoint is not None:
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "resumed",
                "Run resumed after worker retry",
                progress=_progress_for_artifact(artifact),
                snapshot_available=True,
                attempt=attempt,
                max_attempts=max_attempts,
            )
        await self._append_event(
            artifact,
            EventType.RUN,
            "run",
            "started",
            "Run started",
            snapshot_available=True,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        state = checkpoint.state if checkpoint is not None else GraphRunState(
            artifact_id=artifact_id,
            input_data=input_data,
            selected_agents=artifact.run_config.selected_agents,
            resolved_agents=artifact.run_config.resolved_agents,
        )
        graph = cast(Any, self._build_langgraph_app(state.resolved_agents))
        try:
            await graph.ainvoke(self._graph_state_to_dict(state))
        except RunCancelledError:
            artifact = await self._require_artifact(artifact_id)
            artifact.status = RunStatus.CANCELED
            await self._repository.update_artifact(artifact)
        except Exception as error:
            artifact = await self._require_artifact(artifact_id)
            artifact.status = RunStatus.FAILED
            artifact.error_message = str(error)
            error_kind = error.kind if isinstance(error, ProviderError) else None
            provider_name = error.provider_name if isinstance(error, ProviderError) else None
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "failed",
                str(error),
                progress=1.0,
                error_kind=error_kind,
                provider_name=provider_name,
                snapshot_available=True,
            )
            raise
        await self._repository.delete_graph_checkpoint(artifact_id)

    async def _resolve_source(self, input_data: RunInput) -> ExtractedContent:
        """Resolve one source payload into extracted content."""

        if input_data.text:
            content_format = ContentFormat.MARKDOWN
            if input_data.source_type is SourceType.URL and input_data.url:
                provider_name = "url-preview"
            else:
                provider_name = "inline-input"
            return ExtractedContent(
                title=input_data.title or input_data.source_label,
                content=input_data.text,
                content_format=content_format,
                metadata={
                    "provider_name": provider_name,
                    "content_format": content_format.value,
                    "source_type": input_data.source_type.value,
                    "used_inline_content": True,
                },
            )
        if input_data.source_type.value == "url" and input_data.url:
            return await self._extraction_provider.extract(input_data.url)
        return ExtractedContent(
            title=input_data.title or input_data.source_label,
            content="",
            content_format=ContentFormat.MARKDOWN,
            metadata={
                "provider_name": "inline-input",
                "content_format": ContentFormat.MARKDOWN.value,
                "source_type": input_data.source_type.value,
            },
        )

    def _build_langgraph_app(self, resolved_agents: list[str]) -> object:
        """Compile a LangGraph app for one resolved agent plan."""

        graph = StateGraph(LangGraphState)
        graph.add_node("resolve_source", self._langgraph_resolve_source)
        graph.add_node("normalize_document", self._langgraph_normalize_document)
        graph.add_node("plan_agents", self._langgraph_plan_agents)
        graph.add_node("finalize_summary", self._langgraph_finalize_summary)
        graph.add_node("persist_artifact_snapshot", self._langgraph_persist_artifact_snapshot)
        graph.add_node("complete_run", self._langgraph_complete_run)

        definitions = [get_agent_definition(agent_id) for agent_id in resolved_agents]
        for definition in definitions:
            graph.add_node(definition.agent_id, cast(Any, self._langgraph_agent_node(definition)))

        graph.add_edge(START, "resolve_source")
        graph.add_edge("resolve_source", "normalize_document")
        graph.add_edge("normalize_document", "plan_agents")

        roots = [definition for definition in definitions if not definition.depends_on]
        if not roots:
            graph.add_edge("plan_agents", "finalize_summary")
        else:
            for definition in roots:
                graph.add_edge("plan_agents", definition.agent_id)

        downstream_map = {
            definition.agent_id: [item.agent_id for item in definitions if definition.agent_id in item.depends_on]
            for definition in definitions
        }
        sinks = [definition.agent_id for definition in definitions if not downstream_map[definition.agent_id]]

        for definition in definitions:
            for dependency in definition.depends_on:
                graph.add_edge(dependency, definition.agent_id)
            if definition.agent_id in sinks:
                graph.add_edge(definition.agent_id, "finalize_summary")

        graph.add_edge("finalize_summary", "persist_artifact_snapshot")
        graph.add_edge("persist_artifact_snapshot", "complete_run")
        graph.add_edge("complete_run", END)
        return graph.compile()

    async def _langgraph_resolve_source(self, state: LangGraphState) -> dict[str, object]:
        """Resolve source content for one graph run."""

        if "resolve_source" in state.get("completed_nodes", []):
            return {}
        await self._ensure_run_active(state["artifact_id"])
        resolved = await self._resolve_source(state["input_data"])
        artifact = await self._require_artifact(state["artifact_id"])
        await self._append_event(
            artifact,
            EventType.ARTIFACT,
            "extraction",
            "completed",
            _source_message(resolved),
            progress=0.02,
            snapshot_available=True,
            metadata=resolved.metadata,
        )
        updates: dict[str, object] = {
            "extracted_content": resolved.content,
            "extracted_title": resolved.title,
            "extracted_content_format": resolved.content_format,
            "extracted_metadata": resolved.metadata,
            "completed_nodes": ["resolve_source"],
            "node_results": [GraphNodeResult(node_id="resolve_source", status="completed").model_dump(mode="json")],
        }
        await self._checkpoint_graph_state(state, updates)
        return updates

    async def _langgraph_normalize_document(self, state: LangGraphState) -> dict[str, object]:
        """Normalize content into the artifact document."""

        if "normalize_document" in state.get("completed_nodes", []):
            return {}
        await self._ensure_run_active(state["artifact_id"])
        artifact = await self._require_artifact(state["artifact_id"])
        extracted_content = state.get("extracted_content") or state["input_data"].text or ""
        extracted_title = state.get("extracted_title")
        content_format = state.get("extracted_content_format", ContentFormat.PLAIN_TEXT)
        artifact.document = normalize_text(
            state["input_data"],
            extracted_content,
            extracted_title,
            content_format=content_format,
        )
        artifact.source.title = artifact.document.title
        await self._append_event(
            artifact,
            EventType.ARTIFACT,
            "normalization",
            "completed",
            "Document normalized",
            progress=0.05,
            snapshot_available=True,
        )
        updates: dict[str, object] = {
            "completed_nodes": ["normalize_document"],
            "node_results": [
                GraphNodeResult(node_id="normalize_document", status="completed").model_dump(mode="json")
            ],
        }
        await self._checkpoint_graph_state(state, updates)
        return updates

    async def _langgraph_plan_agents(self, state: LangGraphState) -> dict[str, object]:
        """Store a planning checkpoint before agent execution."""

        if "plan_agents" in state.get("completed_nodes", []):
            return {}
        await self._ensure_run_active(state["artifact_id"])
        updates: dict[str, object] = {
            "completed_nodes": ["plan_agents"],
            "node_results": [GraphNodeResult(node_id="plan_agents", status="completed").model_dump(mode="json")],
        }
        await self._checkpoint_graph_state(state, updates)
        return updates

    def _langgraph_agent_node(
        self,
        definition: AgentDefinition,
    ) -> Callable[[LangGraphState], Awaitable[dict[str, object]]]:
        """Build one graph node for an individual agent."""

        async def _run_agent(state: LangGraphState) -> dict[str, object]:
            """Execute one agent and merge its result into the artifact."""

            if definition.agent_id in state.get("completed_agents", []):
                return {}
            await self._ensure_run_active(state["artifact_id"])
            async with self._artifact_lock(state["artifact_id"]):
                artifact = await self._require_artifact(state["artifact_id"])
                plan_item = _require_plan_item(artifact, definition.agent_id)
                if plan_item.status is not AgentPlanStatus.COMPLETED:
                    plan_item.status = AgentPlanStatus.RUNNING
                    plan_item.started_at = datetime.now(UTC)
                    plan_item.message = "Agent running"
                    await self._append_event(
                        artifact,
                        EventType.AGENT,
                        definition.agent_id,
                        "started",
                        f"{definition.display_name} started",
                        progress=_progress_for_artifact(artifact),
                        agent_id=definition.agent_id,
                        agent_name=definition.display_name,
                    )
                    if definition.execution_mode is AgentExecutionMode.MULTI_STEP:
                        await self._append_event(
                            artifact,
                            EventType.AGENT,
                            definition.agent_id,
                            "running",
                            f"{definition.display_name} is gathering intermediate context",
                            progress=_progress_for_artifact(artifact),
                            agent_id=definition.agent_id,
                            agent_name=definition.display_name,
                        )
                result = await self._execute_agent_with_retries(artifact, definition)
                await self._merge_agent_result(artifact, result)

            updates: dict[str, object] = {
                "completed_nodes": [definition.agent_id],
                "completed_agents": [definition.agent_id],
                "node_results": [
                    GraphNodeResult(
                        node_id=definition.agent_id,
                        agent_id=definition.agent_id,
                        status="completed",
                        summary=result.summary,
                        model_name=result.model_name,
                        metadata=result.metadata,
                    ).model_dump(mode="json")
                ],
            }
            await self._checkpoint_graph_state(state, updates)
            return updates

        return _run_agent

    async def _langgraph_finalize_summary(self, state: LangGraphState) -> dict[str, object]:
        """Build the final artifact summary."""

        if "finalize_summary" in state.get("completed_nodes", []):
            return {}
        await self._ensure_run_active(state["artifact_id"])
        artifact = await self._require_artifact(state["artifact_id"])
        artifact.summary = _build_summary(artifact)
        await self._repository.update_artifact(artifact)
        updates: dict[str, object] = {
            "completed_nodes": ["finalize_summary"],
            "node_results": [
                GraphNodeResult(node_id="finalize_summary", status="completed").model_dump(mode="json")
            ],
        }
        await self._checkpoint_graph_state(state, updates)
        return updates

    async def _langgraph_persist_artifact_snapshot(self, state: LangGraphState) -> dict[str, object]:
        """Persist the latest artifact snapshot explicitly."""

        if "persist_artifact_snapshot" in state.get("completed_nodes", []):
            return {}
        await self._ensure_run_active(state["artifact_id"])
        artifact = await self._require_artifact(state["artifact_id"])
        await self._repository.update_artifact(artifact)
        updates: dict[str, object] = {
            "completed_nodes": ["persist_artifact_snapshot"],
            "node_results": [
                GraphNodeResult(node_id="persist_artifact_snapshot", status="completed").model_dump(mode="json")
            ],
        }
        await self._checkpoint_graph_state(state, updates)
        return updates

    async def _langgraph_complete_run(self, state: LangGraphState) -> dict[str, object]:
        """Mark a graph-driven artifact run as completed."""

        if "complete_run" in state.get("completed_nodes", []):
            return {}
        await self._ensure_run_active(state["artifact_id"])
        artifact = await self._require_artifact(state["artifact_id"])
        artifact.status = RunStatus.COMPLETED
        await self._append_event(
            artifact,
            EventType.RUN,
            "run",
            "completed",
            "Run completed",
            progress=1.0,
            snapshot_available=True,
        )
        updates: dict[str, object] = {
            "completed_nodes": ["complete_run"],
            "node_results": [GraphNodeResult(node_id="complete_run", status="completed").model_dump(mode="json")],
        }
        await self._checkpoint_graph_state(state, updates)
        return updates

    async def _queue_batch(self, artifact: AnalysisArtifact, batch: list[AgentDefinition]) -> None:
        """Mark one batch as queued and running."""

        for definition in batch:
            await self._ensure_run_active(artifact.artifact_id)
            plan_item = _require_plan_item(artifact, definition.agent_id)
            plan_item.status = AgentPlanStatus.RUNNING
            plan_item.started_at = datetime.now(UTC)
            plan_item.message = "Agent running"
            await self._append_event(
                artifact,
                EventType.AGENT,
                definition.agent_id,
                "started",
                f"{definition.display_name} started",
                progress=_progress_for_artifact(artifact),
                agent_id=definition.agent_id,
                agent_name=definition.display_name,
            )

    async def _run_batch(self, artifact: AnalysisArtifact, batch: list[AgentDefinition]) -> None:
        """Run one dependency batch and merge results as each task completes."""

        tasks = [
            asyncio.create_task(
                self._execute_agent_with_definition(artifact, definition),
                name=f"agent-{definition.agent_id}",
            )
            for definition in batch
        ]
        for task in asyncio.as_completed(tasks):
            try:
                await self._ensure_run_active(artifact.artifact_id)
                definition, result = await task
            except Exception as error:
                definition = next(
                    (
                        item
                        for item in batch
                        if _require_plan_item(artifact, item.agent_id).status is AgentPlanStatus.RUNNING
                    ),
                    batch[0],
                )
                plan_item = _require_plan_item(artifact, definition.agent_id)
                plan_item.status = AgentPlanStatus.FAILED
                plan_item.completed_at = datetime.now(UTC)
                plan_item.message = str(error)
                await self._append_event(
                    artifact,
                    EventType.AGENT,
                    definition.agent_id,
                    "failed",
                    str(error),
                    progress=_progress_for_artifact(artifact),
                    agent_id=definition.agent_id,
                    agent_name=definition.display_name,
                    attempt=self._agent_max_retries + 1 if isinstance(error, ProviderError) else None,
                    max_attempts=self._agent_max_retries + 1 if isinstance(error, ProviderError) else None,
                    error_kind=error.kind if isinstance(error, ProviderError) else None,
                    provider_name=error.provider_name if isinstance(error, ProviderError) else None,
                    snapshot_available=True,
                )
                raise
            await self._merge_agent_result(artifact, result)
            await self._ensure_run_active(artifact.artifact_id)

    async def _execute_agent_with_definition(
        self,
        artifact: AnalysisArtifact,
        definition: AgentDefinition,
    ) -> tuple[AgentDefinition, AgentExecutionResult]:
        """Execute one agent and preserve its definition for merge ordering."""

        return definition, await self._execute_agent_with_retries(artifact, definition)

    async def _execute_agent(self, artifact: AnalysisArtifact, definition: AgentDefinition) -> AgentExecutionResult:
        """Execute one agent against the current artifact state."""

        await self._ensure_run_active(artifact.artifact_id)
        if artifact.document is None:
            raise ValidationError("Artifact document is missing")
        context = _context_for_agent(artifact, definition)
        instruction = load_instruction_text(definition)
        if definition.provider_kind is ProviderKind.SEARCH:
            query = build_similarity_query(artifact.document.title, artifact.document.blocks)
            results = await self._search_provider.search(query)
            excerpt = artifact.document.blocks[0].text[:120] if artifact.document.blocks else artifact.document.title
            findings = [
                FindingPayload(
                    excerpt=excerpt,
                    rationale=(
                        "Similar public posts cover overlapping ideas, so the article "
                        "should differentiate itself with stronger evidence."
                    ),
                    confidence=max((_score_from_result(item) for item in results), default=0.0),
                    suggestion="Add a distinctive example or a less common framing.",
                )
            ]
            return AgentExecutionResult(
                definition=definition,
                raw_output={"results": results, "query": query},
                findings=findings,
                summary=f"Found {len(results)} related items",
                metadata={"query": query},
                model_name=getattr(self._search_provider, "model_name", "search"),
            )

        if definition.provider_kind is ProviderKind.DEEP_RESEARCH:
            if self._deep_research_provider is None:
                raise ValidationError(
                    f"Agent {definition.agent_id} requires a deep research provider "
                    "but none is configured. Ensure CONTENT_EVAL_OPENAI_API_KEY and "
                    "CONTENT_EVAL_TAVILY_API_KEY are set for live mode."
                )
            instruction = load_instruction_text(definition)
            brief = _build_deep_research_brief(instruction, artifact.document)
            article_text = "\n\n".join(b.text for b in artifact.document.blocks if b.text)
            raw_output = await self._deep_research_provider.fact_check(brief, article_text)
            raw_findings = raw_output.get("findings", [])
            if not isinstance(raw_findings, list):
                raise ValidationError(
                    f"Agent {definition.agent_id} returned an invalid findings payload"
                )
            findings = [FindingPayload.model_validate(item) for item in raw_findings]
            meta = raw_output.get("metadata")
            metadata = meta if isinstance(meta, dict) else {}
            report_sources: list[str] = []
            if isinstance(meta, dict):
                src = meta.get("sources")
                report_sources = [str(s) for s in src] if isinstance(src, list) else []
            findings = [FindingPayload.model_validate(item) for item in raw_findings]
            for f in findings:
                if not f.sources and report_sources:
                    f.sources = report_sources
            return AgentExecutionResult(
                definition=definition,
                raw_output=raw_output,
                findings=findings,
                summary=_coerce_str(raw_output.get("summary")),
                metadata=metadata,
                model_name=self._deep_research_provider.model_name,
            )

        raw_output = await self._analysis_provider.analyze(
            definition.agent_id,
            instruction,
            artifact.document.title,
            artifact.document.blocks,
            context,
            route=_route_for_definition(definition, self._runtime_mode, self._analysis_provider),
        )
        raw_findings = raw_output.get("findings", [])
        if not isinstance(raw_findings, list):
            raise ValidationError(f"Agent {definition.agent_id} returned an invalid findings payload")
        findings = [FindingPayload.model_validate(item) for item in raw_findings]
        return AgentExecutionResult(
            definition=definition,
            raw_output=raw_output,
            findings=findings,
            summary=_coerce_str(raw_output.get("summary")),
            metadata={"instruction_file": definition.instruction_file, "context_keys": sorted(context)},
            model_name=self._analysis_provider.resolve_model_name(
                _route_for_definition(definition, self._runtime_mode, self._analysis_provider)
            ),
        )

    async def _execute_agent_with_retries(
        self,
        artifact: AnalysisArtifact,
        definition: AgentDefinition,
    ) -> AgentExecutionResult:
        """Execute one agent with bounded retries for transient provider failures."""

        total_attempts = self._agent_max_retries + 1
        for attempt in range(1, total_attempts + 1):
            try:
                return await self._execute_agent(artifact, definition)
            except ProviderError as error:
                if not error.retriable or attempt >= total_attempts:
                    raise
                plan_item = _require_plan_item(artifact, definition.agent_id)
                plan_item.status = AgentPlanStatus.RUNNING
                plan_item.message = f"Retry {attempt} of {self._agent_max_retries} after {error.kind.replace('_', ' ')}"
                await self._append_event(
                    artifact,
                    EventType.AGENT,
                    definition.agent_id,
                    "retrying",
                    f"{definition.display_name} retrying after {error.kind.replace('_', ' ')}",
                    progress=_progress_for_artifact(artifact),
                    agent_id=definition.agent_id,
                    agent_name=definition.display_name,
                    attempt=attempt + 1,
                    max_attempts=total_attempts,
                    error_kind=error.kind,
                    provider_name=error.provider_name,
                    snapshot_available=True,
                )
                await asyncio.sleep(min(float(2 ** (attempt - 1)), 5.0))

        raise ProviderError("Agent retry loop exited unexpectedly", kind="provider_error")

    async def _merge_agent_result(self, artifact: AnalysisArtifact, result: AgentExecutionResult) -> None:
        """Merge one completed agent result into the artifact snapshot."""

        if artifact.document is None:
            raise ValidationError("Artifact document is missing")
        plan_item = _require_plan_item(artifact, result.definition.agent_id)
        plan_item.status = AgentPlanStatus.COMPLETED
        plan_item.completed_at = datetime.now(UTC)
        plan_item.model_name = result.model_name
        plan_item.message = "Agent completed"

        resolved_findings: list[AgentFinding] = []
        for finding in result.findings:
            cleaned_excerpt = sanitize_excerpt(finding.excerpt) or finding.excerpt.strip().strip('"')
            anchor = _resolve_anchor(artifact, cleaned_excerpt)
            resolved = AgentFinding(
                category=result.definition.category,
                agent_name=result.definition.agent_id,
                anchor_ids=[anchor.id],
                rationale=finding.rationale,
                confidence=finding.confidence,
                model_name=result.model_name,
                suggestion=finding.suggestion,
                sources=finding.sources,
                metadata={
                    "excerpt": cleaned_excerpt,
                    "anchor_match_kind": anchor.match_kind.value,
                    "matched_to_source": anchor.match_kind == ArtifactAnchorMatchKind.SOURCE,
                    **result.metadata,
                },
            )
            resolved_findings.append(resolved)
            _append_agent_comment(artifact, resolved, artifact.artifact_id, result.definition.display_name)

        artifact.agent_results = [
            item for item in artifact.agent_results if item.agent_id != result.definition.agent_id
        ]
        artifact.agent_results.append(
            ArtifactAgentResult(
                agent_id=result.definition.agent_id,
                category=result.definition.category,
                status=AgentPlanStatus.COMPLETED,
                findings=resolved_findings,
                summary=result.summary,
                raw_output=result.raw_output,
                metadata=result.metadata,
            )
        )
        if artifact.debug is not None:
            artifact.debug.traces.append(
                {
                    "agent_id": result.definition.agent_id,
                    "instruction_file": result.definition.instruction_file,
                    "model_name": result.model_name,
                    "raw_output": result.raw_output,
                    "metadata": result.metadata,
                }
            )
        await self._append_event(
            artifact,
            EventType.AGENT,
            result.definition.agent_id,
            "completed",
            f"{result.definition.display_name} completed",
            progress=_progress_for_artifact(artifact),
            agent_id=result.definition.agent_id,
            agent_name=result.definition.display_name,
            model_name=result.model_name,
            snapshot_available=True,
        )

    async def _append_event(
        self,
        artifact: AnalysisArtifact,
        event_type: EventType,
        stage: str,
        status: str,
        message: str,
        *,
        progress: float | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        model_name: str | None = None,
        attempt: int | None = None,
        max_attempts: int | None = None,
        error_kind: str | None = None,
        provider_name: str | None = None,
        snapshot_available: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Append one event and persist the current artifact."""

        event = ArtifactEvent(
            artifact_id=artifact.artifact_id,
            event_type=event_type,
            stage=stage,
            status=status,
            message=message,
            progress=progress,
            agent_id=agent_id,
            agent_name=agent_name,
            model_name=model_name,
            attempt=attempt,
            max_attempts=max_attempts,
            error_kind=error_kind,
            provider_name=provider_name,
            snapshot_available=snapshot_available,
            metadata=metadata or {},
        )
        artifact.events.append(event)
        artifact.updated_at = datetime.now(UTC)
        await self._repository.update_artifact(artifact)

    async def _require_artifact(self, artifact_id: UUID) -> AnalysisArtifact:
        """Return one artifact or raise."""

        artifact = await self._repository.get_artifact(artifact_id)
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")
        return artifact

    async def _ensure_run_active(self, artifact_id: UUID) -> None:
        """Raise when a run was stopped by the user."""

        artifact = await self._require_artifact(artifact_id)
        if artifact.status is RunStatus.CANCELED:
            raise RunCancelledError("Run stopped by user")

    def _resolve_persistence_mode(self, requested: PersistenceMode) -> PersistenceMode:
        """Return a supported persistence mode."""

        if requested is PersistenceMode.WORKSPACE and not self._persistent_storage_enabled:
            raise ValidationError("Workspace mode requires persistent storage")
        return requested

    async def _checkpoint_graph_state(self, state: LangGraphState, updates: dict[str, object]) -> None:
        """Persist one merged graph checkpoint snapshot."""

        merged = self._merge_graph_state(state, updates)
        await self._repository.save_graph_checkpoint(
            GraphCheckpoint(
                artifact_id=merged.artifact_id,
                state=merged,
            )
        )

    def _merge_graph_state(self, state: LangGraphState, updates: dict[str, object]) -> GraphRunState:
        """Merge one node update into the persisted graph state model."""

        update_errors = _coerce_str_list(updates.get("error_messages"))
        return GraphRunState(
            artifact_id=state["artifact_id"],
            input_data=state["input_data"],
            selected_agents=list(state.get("selected_agents", [])),
            resolved_agents=list(state.get("resolved_agents", [])),
            extracted_content=_coerce_str(updates.get("extracted_content")) or state.get("extracted_content"),
            extracted_title=_coerce_str(updates.get("extracted_title")) or state.get("extracted_title"),
            extracted_content_format=cast(
                ContentFormat,
                updates.get("extracted_content_format") or state.get("extracted_content_format") or ContentFormat.PLAIN_TEXT,
            ),
            extracted_metadata={
                **cast(dict[str, object], state.get("extracted_metadata", {})),
                **cast(dict[str, object], updates.get("extracted_metadata", {})),
            },
            completed_nodes=[*state.get("completed_nodes", []), *_coerce_str_list(updates.get("completed_nodes"))],
            completed_agents=[*state.get("completed_agents", []), *_coerce_str_list(updates.get("completed_agents"))],
            node_results=[
                *[GraphNodeResult.model_validate(item) for item in state.get("node_results", [])],
                *[GraphNodeResult.model_validate(item) for item in _coerce_dict_list(updates.get("node_results"))],
            ],
            error_message=update_errors[-1] if update_errors else None,
            checkpoint_version=_coerce_int(state.get("checkpoint_version")) + 1,
            last_updated_at=datetime.now(UTC),
        )

    def _graph_state_to_dict(self, state: GraphRunState) -> LangGraphState:
        """Convert one persisted graph checkpoint into runtime graph state."""

        return {
            "artifact_id": state.artifact_id,
            "input_data": state.input_data,
            "selected_agents": list(state.selected_agents),
            "resolved_agents": list(state.resolved_agents),
            "extracted_content": state.extracted_content,
            "extracted_title": state.extracted_title,
            "extracted_content_format": state.extracted_content_format,
            "extracted_metadata": dict(state.extracted_metadata),
            "completed_nodes": list(state.completed_nodes),
            "completed_agents": list(state.completed_agents),
            "node_results": [item.model_dump(mode="json") for item in state.node_results],
            "error_messages": [state.error_message] if state.error_message else [],
        }

    def _artifact_lock(self, artifact_id: UUID) -> asyncio.Lock:
        """Return a per-artifact lock for serialized mutation."""

        return self._artifact_locks.setdefault(artifact_id, asyncio.Lock())


def _require_plan_item(artifact: AnalysisArtifact, agent_id: str) -> ArtifactAgentPlanItem:
    """Return one agent plan item."""

    plan_item = next((item for item in artifact.agent_plan if item.agent_id == agent_id), None)
    if plan_item is None:
        raise ValidationError(f"Agent plan item {agent_id} not found")
    return plan_item


def _build_deep_research_brief(instruction: str, document: ArtifactDocument) -> str:
    """Combine the agent instruction with the article content for the research graph."""

    brief = build_fact_check_brief(document.title, document.blocks)
    return f"{instruction}\n\n{brief}"


def _source_message(extracted: ExtractedContent) -> str:
    """Describe how source content was resolved."""

    provider_name = extracted.metadata.get("provider_name")
    fallback_used = extracted.metadata.get("fallback_used") is True
    if provider_name == "url-preview":
        return "Source imported from URL preview"
    if provider_name == "tavily-extract" and fallback_used:
        return "Source extracted via Tavily fallback"
    if provider_name == "tavily-extract":
        return "Source extracted via Tavily"
    if provider_name == "direct":
        return "Source extracted via direct fetch"
    return "Source content resolved"


def _default_agent_ids() -> list[str]:
    """Return the default enabled agents."""

    from content_evaluation.agents.registry import list_agent_definitions

    return [definition.agent_id for definition in list_agent_definitions() if definition.default_enabled]


def _expand_agent_ids(selected_agents: list[str]) -> list[str]:
    """Expand selected agent ids to include dependencies."""

    requested = selected_agents or _default_agent_ids()
    visited: list[str] = []
    visiting: set[str] = set()

    def visit(agent_id: str) -> None:
        """Visit one agent dependency."""

        if agent_id in visiting:
            raise ValidationError(f"Agent dependency cycle detected at {agent_id}")
        if agent_id in visited:
            return
        visiting.add(agent_id)
        try:
            definition = get_agent_definition(agent_id)
        except KeyError as error:
            raise ValidationError(f"Unknown agent id: {agent_id}") from error
        for dependency in definition.depends_on:
            visit(dependency)
        visiting.remove(agent_id)
        visited.append(agent_id)

    for agent_id in requested:
        visit(agent_id)
    return visited


def _plan_order(agent_ids: list[str]) -> list[AgentDefinition]:
    """Return agent definitions in dependency-safe order."""

    return [get_agent_definition(agent_id) for agent_id in agent_ids]


def _execution_batches(agent_ids: list[str]) -> list[list[AgentDefinition]]:
    """Return dependency-safe execution batches."""

    definitions = _plan_order(agent_ids)
    remaining = {definition.agent_id: definition for definition in definitions}
    completed: set[str] = set()
    batches: list[list[AgentDefinition]] = []
    while remaining:
        ready = [
            definition
            for definition in remaining.values()
            if set(definition.depends_on).issubset(completed)
        ]
        if not ready:
            unresolved = ", ".join(sorted(remaining))
            raise ValidationError(f"Could not resolve agent dependencies for: {unresolved}")
        ready.sort(key=lambda definition: definition.agent_id)
        batches.append(ready)
        for definition in ready:
            completed.add(definition.agent_id)
            remaining.pop(definition.agent_id, None)
    return batches


def _context_for_agent(artifact: AnalysisArtifact, definition: AgentDefinition) -> dict[str, object]:
    """Build upstream context for one agent."""

    context: dict[str, object] = {}
    for dependency in definition.depends_on:
        result = next((item for item in artifact.agent_results if item.agent_id == dependency), None)
        if result is not None:
            context[dependency] = _result_context_payload(artifact, result)
    return context


def _append_agent_comment(
    artifact: AnalysisArtifact,
    finding: AgentFinding,
    artifact_id: UUID,
    display_name: str,
) -> None:
    """Attach one top-level agent comment to the artifact."""

    comment = ArtifactComment(
        artifact_id=artifact_id,
        anchor_id=finding.anchor_ids[0],
        author_type=AuthorType.AGENT,
        author_label=f"{display_name} agent",
        category=finding.category,
        body=finding.rationale,
        suggestion=finding.suggestion,
        sources=finding.sources,
        review_state=ReviewState.UNREVIEWED,
    )
    anchor = next(item for item in artifact.anchors if item.id == comment.anchor_id)
    thread = next((item for item in artifact.threads if item.anchor.id == anchor.id), None)
    if thread is None:
        from content_evaluation.domain.models import ArtifactThread

        thread = ArtifactThread(anchor=anchor, comments=[])
        artifact.threads.append(thread)
    thread.comments.append(comment)


def _progress_for_artifact(artifact: AnalysisArtifact) -> float:
    """Compute rough progress for one artifact."""

    if not artifact.agent_plan:
        return 0.0
    completed = sum(1 for item in artifact.agent_plan if item.status is AgentPlanStatus.COMPLETED)
    running = sum(1 for item in artifact.agent_plan if item.status is AgentPlanStatus.RUNNING)
    return min(0.99, (completed + (0.5 if running else 0.0)) / len(artifact.agent_plan))


def _build_summary(artifact: AnalysisArtifact) -> ArtifactSummary:
    """Build the final artifact summary."""

    similarity_result = next((item for item in artifact.agent_results if item.agent_id == "similarity"), None)
    similarity_scores = []
    if similarity_result is not None:
        results = similarity_result.raw_output.get("results", [])
        if isinstance(results, list):
            similarity_scores = [_score_from_result(item) for item in results]

    ai_result = next((item for item in artifact.agent_results if item.agent_id == "ai_likelihood"), None)
    ai_likelihood = 0.0
    if ai_result is not None:
        ai_likelihood = max((finding.confidence for finding in ai_result.findings), default=0.0)

    value_result = next((item for item in artifact.agent_results if item.agent_id == "value"), None)
    audience_result = next((item for item in artifact.agent_results if item.agent_id == "audience"), None)
    synthesis_result = next((item for item in artifact.agent_results if item.agent_id == "synthesis"), None)

    novelty_score = max(0.0, 1.0 - max(similarity_scores or [0.0]))
    value_summary = _first_rationale(value_result)
    audience_summary = _first_rationale(audience_result)
    verdict = _first_rationale(synthesis_result) or "Analysis completed"

    confidence_bonus = sum(
        finding.confidence
        for result in artifact.agent_results
        if result.category in {AgentCategory.VALUE, AgentCategory.AUDIENCE}
        for finding in result.findings
    )
    raw_score = 72 + (confidence_bonus * 10) - (ai_likelihood * 20) - ((1.0 - novelty_score) * 25)
    return ArtifactSummary(
        overall_score=max(0, min(100, int(raw_score))),
        verdict=verdict,
        value_summary=value_summary,
        audience_summary=audience_summary,
        novelty_score=novelty_score,
        ai_likelihood=ai_likelihood,
    )


def _first_rationale(result: ArtifactAgentResult | None) -> str:
    """Return the first rationale from one result."""

    if result is None or not result.findings:
        return ""
    return result.findings[0].rationale


def _coerce_str(value: object) -> str | None:
    """Convert one optional value to a string."""

    if value is None:
        return None
    return str(value)


def _coerce_str_list(value: object) -> list[str]:
    """Convert one optional value into a list of strings."""

    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _coerce_dict_list(value: object) -> list[dict[str, object]]:
    """Convert one optional value into a list of dict objects."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _coerce_int(value: object) -> int:
    """Convert one optional value into an integer."""

    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _route_for_definition(
    definition: AgentDefinition,
    runtime_mode: RuntimeMode,
    analysis_provider: AnalysisProvider,
) -> ProviderRoute | None:
    """Resolve one provider route for an agent definition."""

    del analysis_provider
    if runtime_mode is RuntimeMode.MOCK:
        return None
    return definition.preferred_route


def _score_from_result(item: object) -> float:
    """Return one similarity score from a provider result."""

    if isinstance(item, dict):
        score = item.get("score", 0.0)
        if isinstance(score, (float, int)):
            return float(score)
        if isinstance(score, str):
            try:
                return float(score)
            except ValueError:
                return 0.0
    return 0.0


def _resolve_anchor(artifact: AnalysisArtifact, excerpt: str) -> ArtifactAnchor:
    """Return an existing matching anchor or create a new one."""

    if artifact.document is None:
        raise RuntimeError("Cannot resolve anchors before the document is available")

    cleaned_excerpt = sanitize_excerpt(excerpt)
    candidate_excerpt = cleaned_excerpt or excerpt.strip().strip('"')
    anchor = create_anchor_from_excerpt(artifact.document.blocks, candidate_excerpt)
    if anchor is None:
        anchor = _create_unmatched_anchor(artifact, candidate_excerpt)
    existing = next(
        (
            item
            for item in artifact.anchors
            if item.match_kind == anchor.match_kind
            and item.quote == anchor.quote
            and len(item.segments) == len(anchor.segments)
            and all(
                left.block_id == right.block_id
                and left.start_offset == right.start_offset
                and left.end_offset == right.end_offset
                for left, right in zip(item.segments, anchor.segments, strict=True)
            )
        ),
        None,
    )
    if existing is not None:
        return existing
    artifact.anchors.append(anchor)
    return anchor


def _create_unmatched_anchor(artifact: AnalysisArtifact, excerpt: str) -> ArtifactAnchor:
    """Append one unmatched reference block at the bottom of the document."""

    if artifact.document is None:
        raise RuntimeError("Cannot create unmatched anchors before the document is available")

    heading_block = _ensure_unmatched_heading_block(artifact)
    quote = excerpt.strip().strip('"') or "Referenced text could not be matched to a visible section."
    existing_block = next(
        (
            block
            for block in artifact.document.blocks
            if (
                block.id != heading_block.id
                and block.origin == ArtifactBlockOrigin.SYNTHETIC_UNMATCHED
                and block.markdown == quote
                and block.text == quote
            )
        ),
        None,
    )
    if existing_block is None:
        existing_block = ArtifactBlock(
            index=len(artifact.document.blocks),
            text=quote,
            kind=ArtifactBlockKind.PARAGRAPH,
            origin=ArtifactBlockOrigin.SYNTHETIC_UNMATCHED,
            markdown=quote,
        )
        artifact.document.blocks.append(existing_block)
        artifact.document.text = "\n\n".join(block.text for block in artifact.document.blocks if block.text)

    return ArtifactAnchor(
        quote=quote,
        match_kind=ArtifactAnchorMatchKind.SYNTHETIC_UNMATCHED,
        segments=[
            ArtifactAnchorSegment(
                block_id=existing_block.id,
                start_offset=0,
                end_offset=len(existing_block.text),
            )
        ],
    )


def _ensure_unmatched_heading_block(artifact: AnalysisArtifact) -> ArtifactBlock:
    """Ensure the document contains a bottom-of-page unmatched-reference section."""

    if artifact.document is None:
        raise RuntimeError("Cannot create unmatched blocks before the document is available")

    existing = next(
        (block for block in artifact.document.blocks if block.markdown == "## Unmatched references"),
        None,
    )
    if existing is not None:
        return existing

    block = ArtifactBlock(
        index=len(artifact.document.blocks),
        text="Unmatched references",
        kind=ArtifactBlockKind.HEADING,
        origin=ArtifactBlockOrigin.SYNTHETIC_UNMATCHED,
        markdown="## Unmatched references",
        level=2,
    )
    artifact.document.blocks.append(block)
    artifact.document.text = "\n\n".join(item.text for item in artifact.document.blocks if item.text)
    return block


def _result_context_payload(artifact: AnalysisArtifact, result: ArtifactAgentResult) -> dict[str, object]:
    """Serialize one upstream result without leaking synthetic fallback text."""

    payload = result.model_dump(mode="json")
    serialized_findings: list[dict[str, object]] = []
    for finding in result.findings:
        item = finding.model_dump(mode="json")
        metadata = dict(item.get("metadata", {}))
        linked_anchors = [
            anchor
            for anchor in artifact.anchors
            if anchor.id in finding.anchor_ids
        ]
        matched_to_source = bool(linked_anchors) and all(
            anchor.match_kind == ArtifactAnchorMatchKind.SOURCE for anchor in linked_anchors
        )
        metadata["matched_to_source"] = matched_to_source
        metadata["anchor_match_kind"] = (
            linked_anchors[0].match_kind.value if linked_anchors else ArtifactAnchorMatchKind.SYNTHETIC_UNMATCHED.value
        )
        if matched_to_source:
            item["metadata"] = metadata
        else:
            excerpt = metadata.pop("excerpt", None)
            if isinstance(excerpt, str) and excerpt:
                item["unmatched_excerpt"] = sanitize_excerpt(excerpt) or excerpt
            item["metadata"] = metadata
        serialized_findings.append(item)
    payload["findings"] = serialized_findings
    return payload
