"""Artifact orchestration service."""

from __future__ import annotations

import asyncio
import math
import operator
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
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
    ArtifactDiffItem,
    ArtifactDiffReview,
    ArtifactDocument,
    ArtifactDebug,
    ArtifactEvent,
    ArtifactOverlapItem,
    ArtifactPreviousDraftSnapshot,
    ArtifactRevisedDocument,
    ArtifactReviewSummary,
    ArtifactStructuralCompleteness,
    ArtifactThread,
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
    RevisionMode,
    ReviewState,
    RevisedMarkdownDiffDecision,
    RunConfig,
    RunInput,
    RunMode,
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


@dataclass(frozen=True, slots=True)
class SummaryScoringConfig:
    """Name the tunable weights used to build the top-level summary score."""

    base_score: float = 72.0
    confidence_multiplier: float = 10.0
    ai_likelihood_penalty: float = 20.0
    novelty_penalty_max: float = 25.0


@dataclass(frozen=True, slots=True)
class RevisionSuggestionInput:
    """Store one accepted suggestion used for revised-markdown generation."""

    comment_id: str
    quote: str
    comment: str
    suggestion: str
    author_label: str
    document_revision_id: str | None
    sort_key: tuple[int, int, int, str, datetime, str]


@dataclass(frozen=True, slots=True)
class RevisionReplacement:
    """Store one surgical replacement instruction."""

    anchor: str
    replacement: str


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


class FactCheckClaim(TypedDict):
    """Normalized fact-check claim data used during assembly."""

    claim_text: str
    verdict: str
    evidence_summary: str
    source_links: list[str]
    anchor_excerpt: str
    confidence: float
    suggestion: str | None
    value_add: str
    official_source_links: list[str]
    related_post_links: list[str]


class FactCheckOverlap(TypedDict):
    """Normalized overlap item used during assembly."""

    title: str
    url: str
    note: str
    score: float | None


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
                _build_plan_item(definition)
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

    async def append_agents(self, artifact_id: UUID, selected_agents: list[str]) -> tuple[AnalysisArtifact, RunInput]:
        """Queue additive analysis work on an existing artifact."""

        if not selected_agents:
            raise ValidationError("Select at least one agent to add analysis.")

        async with self._artifact_lock(artifact_id):
            artifact = await self._require_artifact(artifact_id)
            if artifact.status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
                raise ValidationError("Additional analysis is only available after a run has finished.")
            if artifact.document is None:
                raise ValidationError("Artifact must include a normalized document before adding analysis.")

            requested_selected_agents = _union_preserving_order(
                artifact.run_config.selected_agents,
                selected_agents,
            )
            requested_resolved_agents = _expand_agent_ids(requested_selected_agents)
            append_agent_ids = _appendable_agent_ids(artifact, requested_resolved_agents)
            if not append_agent_ids:
                raise ValidationError("No additional agents are available to run for this artifact.")

            artifact.run_config.selected_agents = requested_selected_agents
            artifact.run_config.resolved_agents = _union_preserving_order(
                artifact.run_config.resolved_agents,
                requested_resolved_agents,
            )
            artifact.agent_plan = _merged_agent_plan(
                artifact,
                artifact.run_config.resolved_agents,
                append_agent_ids,
            )
            artifact.status = RunStatus.QUEUED
            artifact.error_message = None
            artifact.summary = None
            artifact.review_summary = None
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "queued",
                "Additional analysis queued",
                progress=_progress_for_artifact(artifact),
                snapshot_available=True,
                metadata={"mode": RunMode.APPEND_AGENTS.value, "append_agent_ids": append_agent_ids},
            )

            input_data = RunInput(
                mode=RunMode.APPEND_AGENTS,
                source_type=artifact.source.source_type,
                source_label=artifact.source.source_label,
                title=artifact.document.title if artifact.document is not None else artifact.source.title,
                url=artifact.source.url,
                selected_agents=requested_selected_agents,
                persistence_mode=artifact.run_config.persistence_mode,
                include_debug_trace=artifact.run_config.include_debug_trace,
            )
            return artifact, input_data

    async def research(
        self,
        artifact_id: UUID,
        prompt: str,
        *,
        anchor_id: str | None = None,
        comment_id: str | None = None,
    ) -> tuple[AnalysisArtifact, RunInput]:
        """Queue targeted follow-up research on an existing artifact."""

        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValidationError("Provide a research prompt.")

        async with self._artifact_lock(artifact_id):
            artifact = await self._require_artifact(artifact_id)
            if artifact.status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
                raise ValidationError("Targeted research is only available after a run has finished.")
            if artifact.document is None:
                raise ValidationError("Artifact must include a normalized document before adding research.")

            research_definition = get_agent_definition("research")
            resolved_anchor_id = _resolve_research_target_anchor_id(
                artifact,
                anchor_id=anchor_id,
                comment_id=comment_id,
            )
            plan_item = _ensure_research_plan_item(artifact, research_definition)
            plan_item.status = AgentPlanStatus.PENDING
            plan_item.started_at = None
            plan_item.completed_at = None
            plan_item.model_name = None
            plan_item.message = "Queued for targeted research"
            artifact.status = RunStatus.QUEUED
            artifact.error_message = None
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "queued",
                "Targeted research queued",
                progress=_progress_for_artifact(artifact),
                snapshot_available=True,
                metadata={
                    "mode": RunMode.RESEARCH.value,
                    "prompt": clean_prompt,
                    "anchor_id": resolved_anchor_id,
                    "comment_id": comment_id,
                },
            )

            input_data = RunInput(
                mode=RunMode.RESEARCH,
                source_type=artifact.source.source_type,
                source_label=artifact.source.source_label,
                title=artifact.document.title if artifact.document is not None else artifact.source.title,
                url=artifact.source.url,
                prompt=clean_prompt,
                anchor_id=resolved_anchor_id,
                comment_id=comment_id,
                selected_agents=[research_definition.agent_id],
                persistence_mode=artifact.run_config.persistence_mode,
                include_debug_trace=artifact.run_config.include_debug_trace,
            )
            return artifact, input_data

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

    async def generate_revised_markdown(
        self,
        artifact_id: UUID,
        *,
        mode: RevisionMode,
        direction_prompt: str | None = None,
    ) -> AnalysisArtifact:
        """Generate candidate revised markdown from accepted suggestions."""

        async with self._artifact_lock(artifact_id):
            artifact = await self._require_artifact(artifact_id)
            if artifact.status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
                raise ValidationError("Revised markdown is only available after a run has finished.")
            if artifact.document is None:
                raise ValidationError("Artifact must include a normalized document before generating revised markdown.")

            accepted_items = _accepted_revision_inputs(artifact)
            if not accepted_items:
                raise ValidationError("Accept at least one agent suggestion before generating revised markdown.")

            original_markdown = artifact.document.raw_content or _document_markdown(artifact.document)
            suggestion_payload = [
                {
                    "comment_id": item.comment_id,
                    "quote": item.quote,
                    "comment": item.comment,
                    "suggestion": item.suggestion,
                    "author_label": item.author_label,
                }
                for item in accepted_items
            ]
            rewrite_payload = await self._analysis_provider.generate_revised_markdown(
                original_markdown,
                suggestion_payload,
                mode,
                direction_prompt=direction_prompt,
                route=_route_for_revision(self._runtime_mode, self._analysis_provider),
            )
            if mode is RevisionMode.SURGICAL:
                replacements = _coerce_revision_replacements(rewrite_payload.get("replacements"))
                candidate_markdown = _apply_replacements(original_markdown, replacements)
            else:
                candidate_markdown = _coerce_str(rewrite_payload.get("markdown"))
            if not candidate_markdown:
                raise ValidationError("Revised markdown generation returned an empty document.")

            artifact.revised_document = ArtifactRevisedDocument(
                mode=mode,
                source_revision_id=artifact.document.revision_id,
                direction_prompt=direction_prompt.strip() if direction_prompt and direction_prompt.strip() else None,
                markdown=candidate_markdown,
                accepted_comment_ids=[item.comment_id for item in accepted_items],
            )
            artifact.diff_review = ArtifactDiffReview(
                mode=mode,
                source_revision_id=artifact.document.revision_id,
                direction_prompt=direction_prompt.strip() if direction_prompt and direction_prompt.strip() else None,
                original_markdown=original_markdown,
                candidate_markdown=candidate_markdown,
                diff_items=_build_diff_items(original_markdown, candidate_markdown),
            )
            await self._append_event(
                artifact,
                EventType.ARTIFACT,
                "revised_markdown",
                "completed",
                "Candidate revised markdown generated",
                snapshot_available=True,
            )
            return artifact

    async def update_diff_review(
        self,
        artifact_id: UUID,
        decisions: list[tuple[str, RevisedMarkdownDiffDecision]],
    ) -> AnalysisArtifact:
        """Persist per-diff review decisions without replacing canonical markdown yet."""

        async with self._artifact_lock(artifact_id):
            artifact = await self._require_artifact(artifact_id)
            if artifact.diff_review is None:
                raise ValidationError("Generate revised markdown before reviewing diffs.")

            decision_map = {diff_id: decision for diff_id, decision in decisions}
            for item in artifact.diff_review.diff_items:
                if item.id in decision_map:
                    item.decision = decision_map[item.id]

            await self._repository.update_artifact(artifact)
            return artifact

    async def apply_diff_review(self, artifact_id: UUID) -> AnalysisArtifact:
        """Apply reviewed diff decisions and promote the accepted markdown."""

        async with self._artifact_lock(artifact_id):
            artifact = await self._require_artifact(artifact_id)
            if artifact.document is None or artifact.diff_review is None:
                raise ValidationError("No revised markdown diff is available to apply.")
            if any(item.decision is RevisedMarkdownDiffDecision.PENDING for item in artifact.diff_review.diff_items):
                raise ValidationError("Review every diff item before applying revised markdown.")

            applied_markdown = _apply_diff_review(artifact.diff_review)
            previous_document = artifact.document.model_copy(deep=True)
            previous_revision_id = previous_document.revision_id
            revised_document = artifact.revised_document.model_copy(deep=True) if artifact.revised_document is not None else None
            preserved_categories = {AgentCategory.FACT_CHECK, AgentCategory.RESEARCH}
            previous_snapshot = _build_previous_draft_snapshot(
                artifact,
                document_revision_id=previous_revision_id,
                preserved_categories=preserved_categories,
            )
            artifact.document = normalize_text(
                RunInput(
                    source_type=artifact.source.source_type,
                    source_label=artifact.source.source_label,
                    title=artifact.document.title,
                    url=artifact.source.url,
                    text=applied_markdown,
                ),
                applied_markdown,
                artifact.document.title,
                content_format=ContentFormat.MARKDOWN,
            )
            new_revision_id = artifact.document.revision_id
            preserved_agent_results = _preserve_historical_agent_results(
                previous_snapshot.agent_results,
                document_revision_id=previous_revision_id,
            )
            preserved_threads = _remap_preserved_threads_to_revision(
                artifact,
                previous_snapshot.threads,
                document_revision_id=previous_revision_id,
            )
            preserved_anchor_ids = {
                thread.anchor.id
                for thread in preserved_threads
            }
            preserved_anchors = [
                anchor
                for anchor in artifact.anchors
                if anchor.id in preserved_anchor_ids
            ]
            artifact.source.title = artifact.document.title
            artifact.agent_plan = []
            artifact.agent_results = preserved_agent_results
            artifact.anchors = preserved_anchors
            artifact.threads = preserved_threads
            artifact.summary = None
            artifact.review_summary = None
            artifact.error_message = None
            artifact.status = RunStatus.COMPLETED
            artifact.previous_draft_snapshot = previous_snapshot
            artifact.revised_document = None
            artifact.diff_review = None
            await self._append_event(
                artifact,
                EventType.ARTIFACT,
                "revised_markdown",
                "applied",
                "Reviewed revised markdown promoted to the working document",
                snapshot_available=True,
                metadata={
                    "mode": revised_document.mode.value if revised_document is not None else None,
                    "source_revision_id": previous_revision_id,
                    "document_revision_id": new_revision_id,
                },
            )
            return artifact

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
            if input_data.mode is RunMode.APPEND_AGENTS:
                await self._process_append_agents(
                    artifact_id, input_data, attempt=attempt, max_attempts=max_attempts
                )
                return
            if input_data.mode is RunMode.RESEARCH:
                await self._process_research(
                    artifact_id, input_data, attempt=attempt, max_attempts=max_attempts
                )
                return
            if self._orchestrator_backend is OrchestratorBackend.LANGGRAPH:
                await self._process_run_with_langgraph(
                    artifact_id, input_data, attempt=attempt, max_attempts=max_attempts
                )
                return
            await self._process_run_legacy(artifact_id, input_data, attempt=attempt, max_attempts=max_attempts)
        finally:
            self._artifact_locks.pop(artifact_id, None)

    async def _process_append_agents(
        self,
        artifact_id: UUID,
        input_data: RunInput,
        *,
        attempt: int,
        max_attempts: int | None,
    ) -> None:
        """Process one queued append-agents job without re-extracting the source."""

        artifact = await self._require_artifact(artifact_id)
        if artifact.document is None:
            raise ValidationError("Artifact document is missing")

        append_agent_ids = _appendable_agent_ids(artifact, _expand_agent_ids(input_data.selected_agents))
        if not append_agent_ids:
            artifact.status = RunStatus.COMPLETED
            artifact.summary = _build_summary(artifact)
            artifact.review_summary = _build_review_summary(artifact)
            await self._repository.update_artifact(artifact)
            return

        artifact.status = RunStatus.RUNNING
        artifact.error_message = None
        if attempt > 1:
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "resumed",
                "Additional analysis resumed after worker retry",
                progress=_progress_for_artifact(artifact),
                snapshot_available=True,
                attempt=attempt,
                max_attempts=max_attempts,
                metadata={"mode": RunMode.APPEND_AGENTS.value},
            )
        await self._append_event(
            artifact,
            EventType.RUN,
            "run",
            "started",
            "Additional analysis started",
            snapshot_available=True,
            attempt=attempt,
            max_attempts=max_attempts,
            metadata={"mode": RunMode.APPEND_AGENTS.value, "append_agent_ids": append_agent_ids},
        )

        try:
            for batch in _execution_batches(append_agent_ids, initially_completed=_completed_agent_ids(artifact)):
                await self._ensure_run_active(artifact_id)
                await self._queue_batch(artifact, batch)
                await self._run_batch(artifact, batch)

            await self._ensure_run_active(artifact_id)
            artifact.summary = _build_summary(artifact)
            artifact.review_summary = _build_review_summary(artifact)
            artifact.status = RunStatus.COMPLETED
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "completed",
                "Additional analysis completed",
                progress=1.0,
                snapshot_available=True,
                metadata={"mode": RunMode.APPEND_AGENTS.value},
            )
        except RunCancelledError:
            artifact = await self._require_artifact(artifact_id)
            artifact.status = RunStatus.CANCELED
            await self._repository.update_artifact(artifact)
        except Exception as error:
            artifact.status = RunStatus.FAILED
            artifact.error_message = str(error)
            await self._append_run_failed_event(
                artifact,
                error,
                progress=1.0,
                mode=RunMode.APPEND_AGENTS,
            )
            raise

    async def _process_research(
        self,
        artifact_id: UUID,
        input_data: RunInput,
        *,
        attempt: int,
        max_attempts: int | None,
    ) -> None:
        """Process one queued targeted-research job without re-extracting the source."""

        artifact = await self._require_artifact(artifact_id)
        if artifact.document is None:
            raise ValidationError("Artifact document is missing")
        if self._deep_research_provider is None:
            raise ValidationError(
                "Targeted research requires a deep research provider. "
                "Ensure CONTENT_EVAL_OPENAI_API_KEY and CONTENT_EVAL_TAVILY_API_KEY are set for live mode."
            )

        research_definition = get_agent_definition("research")
        plan_item = _ensure_research_plan_item(artifact, research_definition)
        target_anchor_id = _resolve_research_target_anchor_id(
            artifact,
            anchor_id=input_data.anchor_id,
            comment_id=input_data.comment_id,
        )

        artifact.status = RunStatus.RUNNING
        artifact.error_message = None
        if attempt > 1:
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "resumed",
                "Targeted research resumed after worker retry",
                progress=_progress_for_artifact(artifact),
                snapshot_available=True,
                attempt=attempt,
                max_attempts=max_attempts,
                metadata={"mode": RunMode.RESEARCH.value},
            )
        await self._append_event(
            artifact,
            EventType.RUN,
            "run",
            "started",
            "Targeted research started",
            snapshot_available=True,
            attempt=attempt,
            max_attempts=max_attempts,
            metadata={
                "mode": RunMode.RESEARCH.value,
                "prompt": input_data.prompt,
                "anchor_id": target_anchor_id,
                "comment_id": input_data.comment_id,
            },
        )

        try:
            await self._ensure_run_active(artifact_id)
            article_text = "\n\n".join(block.text for block in artifact.document.blocks if block.text)
            brief = _build_targeted_research_brief(
                load_instruction_text(research_definition),
                artifact.document,
                input_data.prompt or "",
                target_anchor_id=target_anchor_id,
            )
            raw_output = await self._deep_research_provider.research(brief, article_text)
            claim_findings = _normalize_fact_check_claims(raw_output)
            if not claim_findings:
                raw_findings = raw_output.get("findings", [])
                if isinstance(raw_findings, list):
                    claim_findings = _fallback_fact_check_claims(raw_findings)
            if not claim_findings:
                raise ValidationError("Agent research returned an invalid findings payload")

            meta = raw_output.get("metadata")
            metadata = meta if isinstance(meta, dict) else {}
            dr_usage = _extract_usage_from_metadata(metadata)
            research_summary = _fact_check_research_summary(raw_output)
            result = AgentExecutionResult(
                definition=research_definition,
                raw_output=raw_output,
                findings=[
                    FindingPayload(
                        excerpt=item["anchor_excerpt"],
                        rationale=item["evidence_summary"],
                        confidence=item["confidence"],
                        suggestion=item["suggestion"],
                        sources=list(item["source_links"]),
                        metadata={
                            "claim_text": item["claim_text"],
                            "verdict": item["verdict"],
                            "evidence_summary": item["evidence_summary"],
                            "source_links": list(item["source_links"]),
                            "anchor_excerpt": item["anchor_excerpt"],
                            "value_add": item["value_add"],
                            "official_source_links": list(item["official_source_links"]),
                            "related_post_links": list(item["related_post_links"]),
                        },
                    )
                    for item in claim_findings
                ],
                summary=research_summary,
                metadata={
                    **metadata,
                    "research_summary": research_summary,
                    "target_anchor_id": target_anchor_id,
                    "target_comment_id": input_data.comment_id,
                    "prompt": input_data.prompt,
                },
                model_name=self._deep_research_provider.model_name,
                usage=dr_usage,
            )
            await self._merge_agent_result(
                artifact,
                result,
                replace_existing_results=False,
                anchor_override_id=target_anchor_id,
            )

            await self._ensure_run_active(artifact_id)
            artifact.summary = _build_summary(artifact)
            artifact.review_summary = _build_review_summary(artifact)
            artifact.status = RunStatus.COMPLETED
            plan_item.message = "Agent completed"
            await self._append_event(
                artifact,
                EventType.RUN,
                "run",
                "completed",
                "Targeted research completed",
                progress=1.0,
                snapshot_available=True,
                metadata={
                    "mode": RunMode.RESEARCH.value,
                    "prompt": input_data.prompt,
                    "anchor_id": target_anchor_id,
                    "comment_id": input_data.comment_id,
                },
            )
        except RunCancelledError:
            artifact = await self._require_artifact(artifact_id)
            artifact.status = RunStatus.CANCELED
            await self._repository.update_artifact(artifact)
        except Exception as error:
            artifact.status = RunStatus.FAILED
            artifact.error_message = str(error)
            await self._append_run_failed_event(
                artifact,
                error,
                progress=1.0,
                mode=RunMode.RESEARCH,
            )
            raise

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
            await self._append_run_failed_event(artifact, error, progress=1.0)
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
            await self._append_run_failed_event(artifact, error, progress=1.0)
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
        artifact.review_summary = _build_review_summary(artifact)
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
            claim_findings = _normalize_fact_check_claims(raw_output)
            if not claim_findings:
                raw_findings = raw_output.get("findings", [])
                if isinstance(raw_findings, list):
                    claim_findings = _fallback_fact_check_claims(raw_findings)
            if not claim_findings:
                raise ValidationError(
                    f"Agent {definition.agent_id} returned an invalid findings payload"
                )
            meta = raw_output.get("metadata")
            metadata = meta if isinstance(meta, dict) else {}
            dr_usage = _extract_usage_from_metadata(metadata)
            overlap_items = _normalize_fact_check_overlap_items(raw_output)
            research_summary = _fact_check_research_summary(raw_output)
            tl_dr = _coerce_str(raw_output.get("tl_dr")) or _coerce_str(raw_output.get("tldr"))
            main_claims = _coerce_dict_list(raw_output.get("main_claims"))
            suggested_research_prompt = _coerce_str(metadata.get("suggested_research_prompt")) or _suggest_research_prompt(
                claim_findings[0]["claim_text"] if claim_findings else ""
            )
            findings = [
                FindingPayload(
                    excerpt=item["anchor_excerpt"],
                    rationale=item["evidence_summary"],
                    confidence=item["confidence"],
                    suggestion=item["suggestion"],
                    sources=list(item["source_links"]),
                    metadata={
                        "claim_text": item["claim_text"],
                        "verdict": item["verdict"],
                        "evidence_summary": item["evidence_summary"],
                        "source_links": list(item["source_links"]),
                        "anchor_excerpt": item["anchor_excerpt"],
                        "value_add": item["value_add"],
                        "official_source_links": list(item["official_source_links"]),
                        "related_post_links": list(item["related_post_links"]),
                    },
                )
                for item in claim_findings
            ]
            return AgentExecutionResult(
                definition=definition,
                raw_output=raw_output,
                findings=findings,
                summary=research_summary,
                metadata={
                    **metadata,
                    "research_summary": research_summary,
                    "overlap_items": overlap_items,
                    "tl_dr": tl_dr,
                    "main_claims": main_claims,
                    "suggested_research_prompt": suggested_research_prompt,
                    "inferred_audience": _coerce_str(metadata.get("audience"))
                    or _coerce_str(raw_output.get("inferred_audience")),
                },
                model_name=self._deep_research_provider.model_name,
                usage=dr_usage,
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
        lc_usage = _extract_usage_from_metadata(raw_output)
        return AgentExecutionResult(
            definition=definition,
            raw_output=raw_output,
            findings=findings,
            summary=_coerce_str(raw_output.get("summary")),
            metadata={"instruction_file": definition.instruction_file, "context_keys": sorted(context)},
            model_name=self._analysis_provider.resolve_model_name(
                _route_for_definition(definition, self._runtime_mode, self._analysis_provider)
            ),
            usage=lc_usage,
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

    async def _merge_agent_result(
        self,
        artifact: AnalysisArtifact,
        result: AgentExecutionResult,
        *,
        replace_existing_results: bool = True,
        anchor_override_id: str | None = None,
    ) -> None:
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
            if anchor_override_id is not None:
                anchor = next((item for item in artifact.anchors if item.id == anchor_override_id), None)
                if anchor is None:
                    raise ValidationError(f"Anchor {anchor_override_id} not found")
            else:
                anchor = _resolve_anchor(
                    artifact,
                    cleaned_excerpt,
                    block_id=getattr(finding, "block_id", None),
                )
            resolved = AgentFinding(
                document_revision_id=artifact.document.revision_id,
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
                    **finding.metadata,
                    **result.metadata,
                },
            )
            resolved_findings.append(resolved)
            if _should_create_thread_for_agent(result.definition):
                _append_agent_comment(artifact, resolved, artifact.artifact_id, result.definition.display_name)

        if replace_existing_results:
            artifact.agent_results = [
                item for item in artifact.agent_results if item.agent_id != result.definition.agent_id
            ]
        agent_metadata = dict(result.metadata)
        if result.usage is not None:
            agent_metadata["usage"] = result.usage
        artifact.agent_results.append(
            ArtifactAgentResult(
                agent_id=result.definition.agent_id,
                document_revision_id=artifact.document.revision_id,
                category=result.definition.category,
                status=AgentPlanStatus.COMPLETED,
                findings=resolved_findings,
                summary=result.summary,
                raw_output=result.raw_output,
                metadata=agent_metadata,
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

    async def _append_run_failed_event(
        self,
        artifact: AnalysisArtifact,
        error: Exception,
        *,
        progress: float = 1.0,
        mode: RunMode | None = None,
    ) -> None:
        """Append a standardized failed run event and persist it."""

        metadata = {"mode": mode.value} if mode is not None else None
        error_kind = error.kind if isinstance(error, ProviderError) else None
        provider_name = error.provider_name if isinstance(error, ProviderError) else None
        await self._append_event(
            artifact,
            EventType.RUN,
            "run",
            "failed",
            str(error),
            progress=progress,
            error_kind=error_kind,
            provider_name=provider_name,
            snapshot_available=True,
            metadata=metadata,
        )

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


def _build_plan_item(definition: AgentDefinition) -> ArtifactAgentPlanItem:
    """Create a fresh plan item for one agent definition."""

    return ArtifactAgentPlanItem(
        agent_id=definition.agent_id,
        display_name=definition.display_name,
        category=definition.category,
        depends_on=list(definition.depends_on),
        provider_kind=definition.provider_kind,
        execution_mode=definition.execution_mode,
        instruction_file=str(definition.instruction_path().name),
    )


def _union_preserving_order(existing: list[str], additions: list[str]) -> list[str]:
    """Return the ordered union of two string lists."""

    merged: list[str] = []
    seen: set[str] = set()
    for item in [*existing, *additions]:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _completed_agent_ids(artifact: AnalysisArtifact) -> set[str]:
    """Return agents already completed on the artifact."""

    completed = {
        item.agent_id
        for item in artifact.agent_plan
        if item.status is AgentPlanStatus.COMPLETED
    }
    completed.update(
        result.agent_id
        for result in artifact.agent_results
        if result.status is AgentPlanStatus.COMPLETED
    )
    return completed


def _appendable_agent_ids(artifact: AnalysisArtifact, requested_resolved_agents: list[str]) -> list[str]:
    """Return requested agents that still need to run."""

    completed = _completed_agent_ids(artifact)
    return [agent_id for agent_id in requested_resolved_agents if agent_id not in completed]


def _merged_agent_plan(
    artifact: AnalysisArtifact,
    resolved_agent_ids: list[str],
    append_agent_ids: list[str],
) -> list[ArtifactAgentPlanItem]:
    """Return an updated ordered plan for additive analysis."""

    existing_by_id = {item.agent_id: item.model_copy(deep=True) for item in artifact.agent_plan}
    appendable = set(append_agent_ids)
    completed = _completed_agent_ids(artifact)
    merged: list[ArtifactAgentPlanItem] = []
    for definition in _plan_order(resolved_agent_ids):
        plan_item = existing_by_id.get(definition.agent_id, _build_plan_item(definition))
        if definition.agent_id in completed and plan_item.status is not AgentPlanStatus.COMPLETED:
            plan_item.status = AgentPlanStatus.COMPLETED
            plan_item.message = "Agent completed"
        if definition.agent_id in appendable and definition.agent_id not in completed:
            plan_item.status = AgentPlanStatus.PENDING
            plan_item.started_at = None
            plan_item.completed_at = None
            plan_item.model_name = None
            plan_item.message = "Queued for additional analysis"
        merged.append(plan_item)
    return merged


def _build_deep_research_brief(instruction: str, document: ArtifactDocument) -> str:
    """Combine the agent instruction with the article content for the research graph."""

    brief = build_fact_check_brief(document.title, document.blocks)
    return f"{instruction}\n\n{brief}"


def _build_targeted_research_brief(
    instruction: str,
    document: ArtifactDocument,
    prompt: str,
    *,
    target_anchor_id: str | None = None,
) -> str:
    """Combine a targeted prompt with the article context for follow-up research."""

    prompt_line = prompt.strip() or "Investigate the article's strongest factual claim."
    lines = [
        instruction,
        "",
        "TARGETED RESEARCH REQUEST:",
        prompt_line,
    ]
    if target_anchor_id is not None:
        lines.extend(["Target anchor id:", target_anchor_id])
    lines.extend(["", build_fact_check_brief(document.title, document.blocks)])
    return "\n".join(lines)


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
        if agent_id in selected_agents and not definition.selectable:
            raise ValidationError(f"Agent {agent_id} is no longer available for new runs")
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


def _execution_batches(
    agent_ids: list[str],
    *,
    initially_completed: set[str] | None = None,
) -> list[list[AgentDefinition]]:
    """Return dependency-safe execution batches."""

    definitions = _plan_order(agent_ids)
    remaining = {definition.agent_id: definition for definition in definitions}
    completed: set[str] = set(initially_completed or set())
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
    current_revision_id = artifact.document.revision_id if artifact.document is not None else None
    for dependency in definition.depends_on:
        result = next(
            (
                item
                for item in artifact.agent_results
                if item.agent_id == dependency
                and item.document_revision_id in {None, current_revision_id}
            ),
            None,
        )
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
        document_revision_id=finding.document_revision_id,
        author_type=AuthorType.AGENT,
        author_label=f"{display_name} agent",
        category=finding.category,
        body=finding.rationale,
        suggestion=finding.suggestion,
        sources=finding.sources,
        metadata=dict(finding.metadata),
        review_state=ReviewState.UNREVIEWED,
    )
    anchor = next(item for item in artifact.anchors if item.id == comment.anchor_id)
    thread = next((item for item in artifact.threads if item.anchor.id == anchor.id), None)
    if thread is None:
        thread = ArtifactThread(
            document_revision_id=finding.document_revision_id,
            anchor=anchor,
            comments=[],
        )
        artifact.threads.append(thread)
    thread.comments.append(comment)


def _should_create_thread_for_agent(definition: AgentDefinition) -> bool:
    """Return whether one agent should appear in the comment rail."""

    return definition.category in {
        AgentCategory.AI_LIKELIHOOD,
        AgentCategory.EDITORIAL,
        AgentCategory.FACT_CHECK,
        AgentCategory.RESEARCH,
    }


def _progress_for_artifact(artifact: AnalysisArtifact) -> float:
    """Compute rough progress for one artifact."""

    if not artifact.agent_plan:
        return 0.0
    completed = sum(1 for item in artifact.agent_plan if item.status is AgentPlanStatus.COMPLETED)
    running = sum(1 for item in artifact.agent_plan if item.status is AgentPlanStatus.RUNNING)
    return min(0.99, (completed + (0.5 if running else 0.0)) / len(artifact.agent_plan))


def _result_for_current_revision(
    artifact: AnalysisArtifact,
    *,
    agent_id: str,
) -> ArtifactAgentResult | None:
    """Return one agent result scoped to the current document revision."""

    current_revision_id = artifact.document.revision_id if artifact.document is not None else None
    return next(
        (
            item
            for item in artifact.agent_results
            if item.agent_id == agent_id and item.document_revision_id in {None, current_revision_id}
        ),
        None,
    )


def _build_summary(artifact: AnalysisArtifact) -> ArtifactSummary:
    """Build the final artifact summary."""

    config = SummaryScoringConfig()
    fact_check_result = _result_for_current_revision(artifact, agent_id="fact_check")
    overlap_items = _result_overlap_items(fact_check_result)
    overlap_scores = _result_overlap_scores(fact_check_result, overlap_items)
    overview = _build_overview_data(artifact, fact_check_result)

    ai_result = _result_for_current_revision(artifact, agent_id="ai_likelihood")
    ai_likelihood = 0.0
    if ai_result is not None:
        ai_likelihood = max((finding.confidence for finding in ai_result.findings), default=0.0)

    novelty_score = max(0.0, 1.0 - max(overlap_scores or [0.0]))
    value_summary = _fact_check_value_summary(fact_check_result) or overview["tl_dr"]
    audience_summary = overview["inferred_audience"]
    verdict = (
        _coerce_str(fact_check_result.metadata.get("research_summary")) if fact_check_result is not None else None
    ) or overview["tl_dr"] or "Analysis completed"

    confidence_bonus = sum(finding.confidence for finding in (fact_check_result.findings if fact_check_result else []))
    raw_score = (
        config.base_score
        + (confidence_bonus * config.confidence_multiplier)
        - (ai_likelihood * config.ai_likelihood_penalty)
        - ((1.0 - novelty_score) * config.novelty_penalty_max)
    )
    return ArtifactSummary(
        overall_score=max(0, min(100, int(raw_score))),
        verdict=verdict,
        value_summary=value_summary,
        audience_summary=audience_summary,
        novelty_score=novelty_score,
        ai_likelihood=ai_likelihood,
        tl_dr=overview["tl_dr"],
        word_count=overview["word_count"],
        estimated_reading_time_minutes=overview["estimated_reading_time_minutes"],
    )


def _build_review_summary(artifact: AnalysisArtifact) -> ArtifactReviewSummary | None:
    """Build the narrative summary shown above the document."""

    fact_check_result = _result_for_current_revision(artifact, agent_id="fact_check")
    overview = _build_overview_data(artifact, fact_check_result)
    research_summary = ""
    overlap_items = _result_overlap_items(fact_check_result)
    if fact_check_result is not None:
        research_summary = _coerce_str(fact_check_result.metadata.get("research_summary")) or (
            fact_check_result.summary or ""
        )

    if artifact.document is None and not any([research_summary, overlap_items]):
        return None

    return ArtifactReviewSummary(
        content_summary=overview["tl_dr"],
        research_summary=research_summary,
        tl_dr=overview["tl_dr"],
        inferred_audience=overview["inferred_audience"],
        word_count=overview["word_count"],
        estimated_reading_time_minutes=overview["estimated_reading_time_minutes"],
        article_format=overview["article_format"],
        reading_difficulty=overview["reading_difficulty"],
        structural_completeness=overview["structural_completeness"],
        overlap_items=overlap_items,
    )


def _normalize_fact_check_claims(raw_output: dict[str, object]) -> list[FactCheckClaim]:
    """Normalize fact-check claim payloads into one stable internal shape."""

    claims = _coerce_dict_list(raw_output.get("claim_findings"))
    normalized: list[FactCheckClaim] = []
    for item in claims:
        claim_text = _coerce_str(item.get("claim_text")) or _coerce_str(item.get("claim")) or ""
        evidence_summary = _coerce_str(item.get("evidence_summary")) or _coerce_str(item.get("rationale")) or ""
        anchor_excerpt = _coerce_str(item.get("anchor_excerpt")) or _coerce_str(item.get("excerpt")) or claim_text
        verdict = (_coerce_str(item.get("verdict")) or "UNVERIFIABLE").upper()
        source_links = _coerce_str_list(item.get("source_links") or item.get("sources"))
        confidence = _coerce_float(item.get("confidence")) or 0.0
        suggestion = _coerce_str(item.get("suggestion"))
        value_add = _coerce_str(item.get("value_add")) or ""
        official_source_links = _coerce_str_list(item.get("official_source_links"))
        related_post_links = _coerce_str_list(item.get("related_post_links"))
        if not anchor_excerpt:
            continue
        normalized.append(
            {
                "claim_text": claim_text or anchor_excerpt,
                "verdict": verdict,
                "evidence_summary": evidence_summary or claim_text or anchor_excerpt,
                "source_links": source_links,
                "anchor_excerpt": anchor_excerpt,
                "confidence": confidence,
                "suggestion": suggestion,
                "value_add": value_add,
                "official_source_links": official_source_links or source_links,
                "related_post_links": related_post_links,
            }
        )
    return normalized


def _fallback_fact_check_claims(raw_findings: list[object]) -> list[FactCheckClaim]:
    """Coerce legacy fact-check findings into structured claim entries."""

    normalized: list[FactCheckClaim] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        excerpt = _coerce_str(item.get("excerpt")) or ""
        rationale = _coerce_str(item.get("rationale")) or ""
        if not excerpt:
            continue
        normalized.append(
            {
                "claim_text": excerpt,
                "verdict": _infer_fact_check_verdict(rationale),
                "evidence_summary": rationale,
                "source_links": _coerce_str_list(item.get("sources")),
                "anchor_excerpt": excerpt,
                "confidence": _coerce_float(item.get("confidence")) or 0.0,
                "suggestion": _coerce_str(item.get("suggestion")),
                "value_add": "",
                "official_source_links": _coerce_str_list(item.get("official_source_links") or item.get("sources")),
                "related_post_links": _coerce_str_list(item.get("related_post_links")),
            }
        )
    return normalized


def _normalize_fact_check_overlap_items(raw_output: dict[str, object]) -> list[FactCheckOverlap]:
    """Normalize overlap research items from fact-check output."""

    items = _coerce_dict_list(raw_output.get("overlap_items"))
    normalized: list[FactCheckOverlap] = []
    for item in items:
        title = _coerce_str(item.get("title")) or ""
        url = _coerce_str(item.get("url")) or ""
        note = _coerce_str(item.get("overlap_note")) or _coerce_str(item.get("note")) or ""
        score = _coerce_float(item.get("score"))
        if title and url:
            normalized.append(
                {
                    "title": title,
                    "url": url,
                    "note": note,
                    "score": score,
                }
            )
    return normalized


def _fact_check_research_summary(raw_output: dict[str, object]) -> str | None:
    """Return the normalized research summary from fact-check output."""

    return _coerce_str(raw_output.get("research_summary")) or _coerce_str(raw_output.get("summary"))


def _infer_fact_check_verdict(text: str) -> str:
    """Infer one fact-check verdict from legacy prose."""

    normalized = text.upper()
    for verdict in ("SUPPORTED", "REFUTED", "MIXED", "UNVERIFIABLE"):
        if verdict in normalized:
            return verdict
    return "UNVERIFIABLE"


def _result_overlap_items(result: ArtifactAgentResult | None) -> list[ArtifactOverlapItem]:
    """Extract typed overlap items from one stored agent result."""

    if result is None:
        return []
    raw_items = result.metadata.get("overlap_items")
    if not isinstance(raw_items, list):
        return []
    overlap_items: list[ArtifactOverlapItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = _coerce_str(item.get("title")) or ""
        url = _coerce_str(item.get("url")) or ""
        note = _coerce_str(item.get("note")) or ""
        if title and url:
            overlap_items.append(ArtifactOverlapItem(title=title, url=url, note=note))
    return overlap_items


def _fact_check_overlap_score(item: ArtifactOverlapItem) -> float | None:
    """Infer an overlap score from one overlap item note when explicit scores are unavailable."""

    note = item.note.lower()
    if "high overlap" in note:
        return 0.8
    if "moderate overlap" in note:
        return 0.55
    if "low overlap" in note:
        return 0.25
    return None


def _result_overlap_scores(
    result: ArtifactAgentResult | None,
    overlap_items: list[ArtifactOverlapItem],
) -> list[float]:
    """Return overlap scores from structured metadata with note-based fallback."""

    if result is None:
        return []
    raw_items = result.metadata.get("overlap_items")
    if isinstance(raw_items, list):
        direct_scores = [
            score
            for score in (_coerce_float(item.get("score")) for item in raw_items if isinstance(item, dict))
            if score is not None
        ]
        if direct_scores:
            return direct_scores
    return [score for score in (_fact_check_overlap_score(item) for item in overlap_items) if score is not None]


def _first_rationale(result: ArtifactAgentResult | None) -> str:
    """Return the first rationale from one result."""

    if result is None or not result.findings:
        return ""
    return result.findings[0].rationale


def _fact_check_value_summary(result: ArtifactAgentResult | None) -> str:
    """Return the value-oriented summary now supplied by fact-check."""

    if result is None:
        return ""
    return (
        _coerce_str(result.metadata.get("value_summary"))
        or _coerce_str(result.metadata.get("differentiation_summary"))
        or _first_rationale(result)
    )


def _build_overview_data(
    artifact: AnalysisArtifact,
    fact_check_result: ArtifactAgentResult | None,
) -> dict[str, object]:
    """Build overview-only summary data directly from the article and artifact."""

    document = artifact.document
    if document is None:
        return {
            "tl_dr": "",
            "inferred_audience": "",
            "word_count": 0,
            "estimated_reading_time_minutes": 0,
            "article_format": "",
            "reading_difficulty": "",
            "structural_completeness": ArtifactStructuralCompleteness(),
        }

    source_blocks = [block for block in document.blocks if block.origin is ArtifactBlockOrigin.SOURCE and block.text.strip()]
    word_count = sum(len(block.text.split()) for block in source_blocks)
    estimated_reading_time_minutes = max(1, math.ceil(word_count / 220)) if word_count else 0
    fact_check_metadata = fact_check_result.metadata if fact_check_result is not None else {}
    tl_dr = (
        _coerce_str(fact_check_metadata.get("tl_dr"))
        or _coerce_str(fact_check_metadata.get("tldr"))
        or _summarize_lead_blocks(source_blocks)
    )
    inferred_audience = (
        _coerce_str(fact_check_metadata.get("inferred_audience"))
        or _coerce_str(fact_check_metadata.get("audience_overview"))
        or _infer_audience_from_text(document.text)
    )
    article_format = (
        _coerce_str(fact_check_metadata.get("article_format"))
        or _guess_article_format(document)
    )
    reading_difficulty = (
        _coerce_str(fact_check_metadata.get("reading_difficulty"))
        or _estimate_reading_difficulty(source_blocks)
    )
    structural_completeness = _structural_completeness_from_metadata(fact_check_metadata) or _structural_completeness(
        document
    )
    return {
        "tl_dr": tl_dr,
        "inferred_audience": inferred_audience,
        "word_count": word_count,
        "estimated_reading_time_minutes": estimated_reading_time_minutes,
        "article_format": article_format,
        "reading_difficulty": reading_difficulty,
        "structural_completeness": structural_completeness,
    }


def _extract_usage_from_metadata(payload: dict[str, object]) -> dict[str, int] | None:
    """Pop normalized token-usage metadata from one provider payload."""

    raw_usage = payload.pop("usage", None)
    if not isinstance(raw_usage, dict):
        return None
    return {
        key: int(value)
        for key, value in raw_usage.items()
        if isinstance(value, (int, float))
    }


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


def _coerce_float(value: object) -> float | None:
    """Convert one optional value into a float."""

    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


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


def _accepted_revision_inputs(artifact: AnalysisArtifact) -> list[RevisionSuggestionInput]:
    """Return accepted agent suggestions in stable article order."""

    if artifact.document is None:
        return []

    current_revision_id = artifact.document.revision_id
    block_index_by_id = {block.id: block.index for block in artifact.document.blocks}
    items: list[RevisionSuggestionInput] = []
    for thread in artifact.threads:
        if thread.document_revision_id not in {None, current_revision_id}:
            continue
        for comment in thread.comments:
            if comment.author_type is not AuthorType.AGENT:
                continue
            if comment.review_state is not ReviewState.ACCEPTED or not comment.suggestion:
                continue
            if comment.document_revision_id not in {None, current_revision_id}:
                continue
            primary = thread.anchor.segments[0]
            items.append(
                RevisionSuggestionInput(
                    comment_id=comment.id,
                    quote=_compact_text(thread.anchor.quote),
                    comment=_compact_text(comment.body),
                    suggestion=_compact_text(comment.suggestion),
                    author_label=comment.author_label,
                    document_revision_id=comment.document_revision_id or thread.document_revision_id,
                    sort_key=(
                        1 if thread.anchor.match_kind == ArtifactAnchorMatchKind.SYNTHETIC_UNMATCHED else 0,
                        block_index_by_id.get(primary.block_id, 10**9),
                        primary.start_offset,
                        thread.anchor.id,
                        comment.created_at,
                        comment.id,
                    ),
                )
            )
    items.sort(key=lambda item: item.sort_key)
    return items


def _coerce_revision_replacements(value: object) -> list[RevisionReplacement]:
    """Return validated surgical replacement instructions."""

    if not isinstance(value, list):
        return []
    replacements: list[RevisionReplacement] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        anchor = _coerce_str(item.get("anchor")).strip()
        replacement = _coerce_str(item.get("replacement")).strip()
        if not anchor or not replacement:
            continue
        replacements.append(RevisionReplacement(anchor=anchor, replacement=replacement))
    return replacements


def _apply_replacements(original_markdown: str, replacements: list[RevisionReplacement]) -> str:
    """Apply surgical replacements to the original markdown in order."""

    revised = original_markdown.strip()
    for item in replacements:
        if item.anchor not in revised:
            continue
        revised = revised.replace(item.anchor, item.replacement, 1)
    return revised


def _build_previous_draft_snapshot(
    artifact: AnalysisArtifact,
    *,
    document_revision_id: str,
    preserved_categories: set[AgentCategory],
) -> ArtifactPreviousDraftSnapshot:
    """Archive the immediately previous draft and preserved findings."""

    if artifact.document is None:
        raise ValidationError("Artifact document is missing")

    preserved_threads: list[ArtifactThread] = []
    for thread in artifact.threads:
        preserved_comments = [
            comment.model_copy(deep=True)
            for comment in thread.comments
            if comment.category in preserved_categories
        ]
        if not preserved_comments:
            continue
        preserved_threads.append(
            ArtifactThread(
                document_revision_id=thread.document_revision_id,
                anchor=thread.anchor.model_copy(deep=True),
                comments=preserved_comments,
            )
        )
    preserved_anchor_ids = {thread.anchor.id for thread in preserved_threads}
    preserved_anchors = [
        anchor.model_copy(deep=True)
        for anchor in artifact.anchors
        if anchor.id in preserved_anchor_ids
    ]
    preserved_results = [
        result.model_copy(deep=True)
        for result in artifact.agent_results
        if result.category in preserved_categories
    ]
    return ArtifactPreviousDraftSnapshot(
        document_revision_id=document_revision_id,
        document=artifact.document.model_copy(deep=True),
        anchors=preserved_anchors,
        threads=preserved_threads,
        agent_results=preserved_results,
    )


def _preserve_historical_agent_results(
    results: list[ArtifactAgentResult],
    *,
    document_revision_id: str,
) -> list[ArtifactAgentResult]:
    """Keep preserved fact-check and research results tied to the old revision."""

    preserved: list[ArtifactAgentResult] = []
    for result in results:
        clone = result.model_copy(deep=True)
        clone.document_revision_id = document_revision_id
        for finding in clone.findings:
            finding.document_revision_id = document_revision_id
            finding.metadata["historical"] = True
            finding.metadata["document_revision_id"] = document_revision_id
        clone.metadata["historical"] = True
        clone.metadata["document_revision_id"] = document_revision_id
        preserved.append(clone)
    return preserved


def _remap_preserved_threads_to_revision(
    artifact: AnalysisArtifact,
    threads: list[ArtifactThread],
    *,
    document_revision_id: str,
) -> list[ArtifactThread]:
    """Clone preserved historical threads that still anchor honestly into the new draft."""

    if artifact.document is None:
        raise ValidationError("Artifact document is missing")

    remapped_threads: list[ArtifactThread] = []
    for thread in threads:
        matched_anchor = create_anchor_from_excerpt(artifact.document.blocks, thread.anchor.quote)
        if matched_anchor is None:
            continue
        existing_anchor = _resolve_anchor(artifact, thread.anchor.quote, block_id=matched_anchor.segments[0].block_id)
        existing_anchor.document_revision_id = document_revision_id
        clone = thread.model_copy(deep=True)
        clone.anchor = existing_anchor
        clone.document_revision_id = document_revision_id
        for comment in clone.comments:
            comment.document_revision_id = document_revision_id
            comment.metadata["historical"] = True
            comment.metadata["document_revision_id"] = document_revision_id
        remapped_threads.append(clone)
    return remapped_threads


def _document_markdown(document: ArtifactDocument) -> str:
    """Render canonical markdown from a normalized document when raw content is absent."""

    return "\n\n".join((block.markdown or block.text).strip() for block in document.blocks if block.text.strip())


def _build_diff_items(original_markdown: str, candidate_markdown: str) -> list[ArtifactDiffItem]:
    """Build deterministic diff items from whole-document markdown comparison."""

    original_lines = original_markdown.splitlines()
    candidate_lines = candidate_markdown.splitlines()
    matcher = SequenceMatcher(a=original_lines, b=candidate_lines)
    items: list[ArtifactDiffItem] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        items.append(
            ArtifactDiffItem(
                change_type=tag,
                original_start_line=i1 + 1,
                original_end_line=i2,
                candidate_start_line=j1 + 1,
                candidate_end_line=j2,
                before_text="\n".join(original_lines[i1:i2]),
                after_text="\n".join(candidate_lines[j1:j2]),
            )
        )
    return items


def _apply_diff_review(diff_review: ArtifactDiffReview) -> str:
    """Apply accepted and rejected diff decisions to reconstruct the next working markdown."""

    original_lines = diff_review.original_markdown.splitlines()
    applied_lines: list[str] = []
    cursor = 0
    for item in sorted(diff_review.diff_items, key=lambda diff: (diff.original_start_line, diff.original_end_line, diff.id)):
        start = max(0, item.original_start_line - 1)
        end = max(start, item.original_end_line)
        applied_lines.extend(original_lines[cursor:start])
        if item.decision is RevisedMarkdownDiffDecision.ACCEPTED:
            applied_lines.extend(item.after_text.splitlines())
        else:
            applied_lines.extend(original_lines[start:end])
        cursor = end
    applied_lines.extend(original_lines[cursor:])
    return "\n".join(applied_lines).strip()


def _compact_text(value: str) -> str:
    """Collapse whitespace for revision prompts and deterministic sorting."""

    return " ".join(value.split())


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


def _route_for_revision(
    runtime_mode: RuntimeMode,
    analysis_provider: AnalysisProvider,
) -> ProviderRoute | None:
    """Resolve provider routing for revised-markdown generation."""

    del analysis_provider
    if runtime_mode is RuntimeMode.MOCK:
        return None
    return None


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


def _resolve_anchor(artifact: AnalysisArtifact, excerpt: str, *, block_id: str | None = None) -> ArtifactAnchor:
    """Return an existing matching anchor or create a new one."""

    if artifact.document is None:
        raise RuntimeError("Cannot resolve anchors before the document is available")

    cleaned_excerpt = sanitize_excerpt(excerpt)
    candidate_excerpt = cleaned_excerpt or excerpt.strip().strip('"')
    anchor = create_anchor_from_excerpt(artifact.document.blocks, candidate_excerpt, block_id=block_id)
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
        if existing.document_revision_id is None and artifact.document is not None:
            existing.document_revision_id = artifact.document.revision_id
        return existing
    if artifact.document is not None:
        anchor.document_revision_id = artifact.document.revision_id
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
        document_revision_id=artifact.document.revision_id,
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

    payload: dict[str, object] = {
        "agent_id": result.agent_id,
        "category": result.category.value,
        "status": result.status.value,
        "summary": result.summary,
        "metadata": {
            key: value
            for key, value in result.metadata.items()
            if key
            in {
                "research_summary",
                "overlap_items",
                "usage",
                "instruction_file",
                "context_keys",
                "suggested_research_prompt",
            }
        },
    }
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
        if linked_anchors:
            metadata["block_id"] = linked_anchors[0].segments[0].block_id
            metadata["quote"] = linked_anchors[0].quote
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


_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def _summarize_lead_blocks(blocks: list[ArtifactBlock]) -> str:
    """Return a compact TL;DR from the opening source blocks."""

    text = " ".join(block.text.strip() for block in blocks[:2] if block.text.strip())
    if not text:
        return ""
    sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT_PATTERN.split(text) if sentence.strip()]
    summary = " ".join(sentences[:2]) if sentences else text
    return summary[:240].rstrip()


def _infer_audience_from_text(text: str) -> str:
    """Guess a broad audience label from the article text."""

    lowered = text.lower()
    if any(keyword in lowered for keyword in ("editor", "editorial", "content strategy", "blog")):
        return "Editorial and content teams"
    if any(keyword in lowered for keyword in ("developer", "engineering", "code", "api")):
        return "Technical practitioners and builders"
    if any(keyword in lowered for keyword in ("founder", "growth", "marketing", "sales")):
        return "Operators, founders, and go-to-market teams"
    return "General readers interested in the topic"


def _guess_article_format(document: ArtifactDocument) -> str:
    """Guess the article format from the title and block structure."""

    title = document.title.lower()
    text = document.text.lower()
    if "how to" in title or "tutorial" in title or any(block.kind is ArtifactBlockKind.CODE for block in document.blocks):
        return "tutorial"
    if "announcing" in title or "launch" in title or "release" in title:
        return "announcement"
    if "case study" in title or "we " in text[:400] or "i " in text[:400]:
        return "case_study"
    if len([block for block in document.blocks if block.kind is ArtifactBlockKind.HEADING]) >= 4:
        return "roundup"
    return "article"


def _estimate_reading_difficulty(blocks: list[ArtifactBlock]) -> str:
    """Return a coarse density indicator for the article."""

    if not blocks:
        return ""
    total_words = sum(len(block.text.split()) for block in blocks)
    average_words = total_words / max(len(blocks), 1)
    if average_words >= 90:
        return "dense"
    if average_words >= 45:
        return "moderate"
    return "accessible"


def _structural_completeness(document: ArtifactDocument) -> ArtifactStructuralCompleteness:
    """Return lightweight structural completeness signals."""

    source_blocks = [block for block in document.blocks if block.origin is ArtifactBlockOrigin.SOURCE and block.text.strip()]
    headings = [block for block in source_blocks if block.kind is ArtifactBlockKind.HEADING]
    intro_text = source_blocks[0].text.lower() if source_blocks else ""
    closing_text = source_blocks[-1].text.lower() if source_blocks else ""
    return ArtifactStructuralCompleteness(
        has_intro=bool(intro_text),
        has_headings=bool(headings),
        has_conclusion=any(
            phrase in closing_text for phrase in ("in summary", "overall", "bottom line", "in conclusion", "to sum up")
        ),
    )


def _structural_completeness_from_metadata(metadata: dict[str, object]) -> ArtifactStructuralCompleteness | None:
    """Parse structural completeness from fact-check metadata when present."""

    raw = metadata.get("structural_completeness")
    if not isinstance(raw, dict):
        return None
    return ArtifactStructuralCompleteness(
        has_intro=bool(raw.get("has_intro")),
        has_headings=bool(raw.get("has_headings")),
        has_conclusion=bool(raw.get("has_conclusion")),
    )


def _ensure_research_plan_item(
    artifact: AnalysisArtifact,
    definition: AgentDefinition,
) -> ArtifactAgentPlanItem:
    """Create or reset the targeted research plan item."""

    existing = next((item for item in artifact.agent_plan if item.agent_id == definition.agent_id), None)
    if existing is not None:
        return existing
    plan_item = _build_plan_item(definition)
    artifact.agent_plan.append(plan_item)
    return plan_item


def _resolve_research_target_anchor_id(
    artifact: AnalysisArtifact,
    *,
    anchor_id: str | None,
    comment_id: str | None,
) -> str | None:
    """Resolve the target anchor for one targeted research request."""

    resolved_anchor_id = anchor_id
    if comment_id is not None:
        comment = _find_comment_in_artifact(artifact, comment_id)
        if comment is None:
            raise ValidationError(f"Comment {comment_id} not found")
        if resolved_anchor_id is not None and resolved_anchor_id != comment.anchor_id:
            raise ValidationError("comment_id and anchor_id must reference the same thread")
        resolved_anchor_id = comment.anchor_id

    if resolved_anchor_id is not None and not any(anchor.id == resolved_anchor_id for anchor in artifact.anchors):
        raise ValidationError(f"Anchor {resolved_anchor_id} not found")
    return resolved_anchor_id


def _find_comment_in_artifact(artifact: AnalysisArtifact, comment_id: str) -> ArtifactComment | None:
    """Return one comment from an artifact when present."""

    for thread in artifact.threads:
        for comment in thread.comments:
            if comment.id == comment_id:
                return comment
    return None


def _suggest_research_prompt(seed: str) -> str:
    """Build a concise prompt for targeted research follow-ups."""

    compact = " ".join(seed.split()).strip()
    if not compact:
        compact = "the article's strongest factual claim"
    return f"Investigate whether {compact[:120]} is supported by primary sources."
