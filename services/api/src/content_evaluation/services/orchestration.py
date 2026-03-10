"""Artifact orchestration service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from content_evaluation.agents.registry import (
    AgentDefinition,
    FindingPayload,
    get_agent_definition,
    load_instruction_text,
)
from content_evaluation.domain.exceptions import NotFoundError, ValidationError
from content_evaluation.domain.models import (
    AgentCatalogEntry,
    AgentCategory,
    AgentFinding,
    AgentPlanStatus,
    AnalysisArtifact,
    ArtifactAgentPlanItem,
    ArtifactAgentResult,
    ArtifactAnchor,
    ArtifactComment,
    ArtifactDebug,
    ArtifactEvent,
    ArtifactSource,
    ArtifactSummary,
    AuthorType,
    EventType,
    PersistenceMode,
    ProviderKind,
    ReviewState,
    RunConfig,
    RunInput,
    RunStatus,
    RuntimeMode,
)
from content_evaluation.providers.interfaces.analysis import AnalysisProvider
from content_evaluation.providers.interfaces.extraction import ContentExtractionProvider
from content_evaluation.providers.interfaces.search import SimilaritySearchProvider
from content_evaluation.repositories.base import RunRepository
from content_evaluation.services.anchors import create_anchor_from_excerpt
from content_evaluation.services.normalization import build_similarity_query, normalize_text


@dataclass(slots=True)
class AgentExecutionResult:
    """Hold one completed agent execution result."""

    definition: AgentDefinition
    raw_output: dict[str, object]
    findings: list[FindingPayload]
    summary: str | None
    metadata: dict[str, object]
    model_name: str


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
    ) -> None:
        """Initialize the orchestrator."""

        self._repository = repository
        self._analysis_provider = analysis_provider
        self._search_provider = search_provider
        self._extraction_provider = extraction_provider
        self._runtime_mode = runtime_mode
        self._persistent_storage_enabled = persistent_storage_enabled

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
        return await self._repository.create_artifact(artifact)

    async def import_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist one imported artifact."""

        artifact.source.imported = True
        artifact.run_config.persistence_mode = self._resolve_persistence_mode(artifact.run_config.persistence_mode)
        existing = await self._repository.get_artifact(artifact.artifact_id)
        if existing is None:
            return await self._repository.create_artifact(artifact)
        return await self._repository.update_artifact(artifact)

    async def process_run(self, artifact_id: UUID, input_data: RunInput) -> None:
        """Process one queued artifact."""

        artifact = await self._require_artifact(artifact_id)
        artifact.status = RunStatus.RUNNING
        artifact.error_message = None
        await self._append_event(artifact, EventType.RUN, "run", "started", "Run started", snapshot_available=True)

        try:
            extracted = await self._resolve_source(input_data)
            artifact.document = normalize_text(input_data, extracted["text"], extracted.get("title"))
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
                await self._queue_batch(artifact, batch)
                await self._run_batch(artifact, batch)

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
        except Exception as error:
            artifact.status = RunStatus.FAILED
            artifact.error_message = str(error)
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "failed",
                str(error),
                progress=1.0,
                snapshot_available=True,
            )
            raise

    async def _resolve_source(self, input_data: RunInput) -> dict[str, str]:
        """Resolve one source payload into text and title."""

        if input_data.source_type.value == "url" and input_data.url:
            return await self._extraction_provider.extract(input_data.url)
        text = input_data.text or ""
        return {"title": input_data.title or input_data.source_label, "text": text}

    async def _queue_batch(self, artifact: AnalysisArtifact, batch: list[AgentDefinition]) -> None:
        """Mark one batch as queued and running."""

        for definition in batch:
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
                )
                raise
            await self._merge_agent_result(artifact, result)

    async def _execute_agent_with_definition(
        self,
        artifact: AnalysisArtifact,
        definition: AgentDefinition,
    ) -> tuple[AgentDefinition, AgentExecutionResult]:
        """Execute one agent and preserve its definition for merge ordering."""

        return definition, await self._execute_agent(artifact, definition)

    async def _execute_agent(self, artifact: AnalysisArtifact, definition: AgentDefinition) -> AgentExecutionResult:
        """Execute one agent against the current artifact state."""

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

        raw_output = await self._analysis_provider.analyze(
            definition.agent_id,
            instruction,
            artifact.document.title,
            artifact.document.blocks,
            context,
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
            model_name=getattr(self._analysis_provider, "model_name", "analysis"),
        )

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
            anchor = _resolve_anchor(artifact, finding.excerpt)
            resolved = AgentFinding(
                category=result.definition.category,
                agent_name=result.definition.agent_id,
                anchor_ids=[anchor.id],
                rationale=finding.rationale,
                confidence=finding.confidence,
                model_name=result.model_name,
                suggestion=finding.suggestion,
                metadata={"excerpt": finding.excerpt, **result.metadata},
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
        snapshot_available: bool = False,
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
            snapshot_available=snapshot_available,
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

    def _resolve_persistence_mode(self, requested: PersistenceMode) -> PersistenceMode:
        """Return a supported persistence mode."""

        if requested is PersistenceMode.WORKSPACE and not self._persistent_storage_enabled:
            raise ValidationError("Workspace mode requires persistent storage")
        return requested


def _require_plan_item(artifact: AnalysisArtifact, agent_id: str) -> ArtifactAgentPlanItem:
    """Return one agent plan item."""

    plan_item = next((item for item in artifact.agent_plan if item.agent_id == agent_id), None)
    if plan_item is None:
        raise ValidationError(f"Agent plan item {agent_id} not found")
    return plan_item


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
            context[dependency] = result.model_dump(mode="json")
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

    anchor = create_anchor_from_excerpt(artifact.document.blocks, excerpt)
    existing = next(
        (
            item
            for item in artifact.anchors
            if item.block_id == anchor.block_id
            and item.start_offset == anchor.start_offset
            and item.end_offset == anchor.end_offset
            and item.quote == anchor.quote
        ),
        None,
    )
    if existing is not None:
        return existing
    artifact.anchors.append(anchor)
    return anchor
