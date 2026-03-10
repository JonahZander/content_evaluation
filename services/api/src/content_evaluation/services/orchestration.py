"""Run orchestration service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from content_evaluation.domain.models import (
    AgentCategory,
    AgentFinding,
    AuthorType,
    Comment,
    ReviewState,
    RunEvent,
    RunInput,
    RunMetadata,
    RunStatus,
    RunSummary,
    SourceType,
)
from content_evaluation.providers.interfaces.analysis import AnalysisProvider
from content_evaluation.providers.interfaces.extraction import ContentExtractionProvider
from content_evaluation.providers.interfaces.search import SimilaritySearchProvider
from content_evaluation.repositories.base import RunRepository
from content_evaluation.services.anchors import create_anchor_from_excerpt
from content_evaluation.services.normalization import build_similarity_query, normalize_text


class RunOrchestrator:
    """Create runs and orchestrate all analysis steps."""

    def __init__(
        self,
        repository: RunRepository,
        analysis_provider: AnalysisProvider,
        search_provider: SimilaritySearchProvider,
        extraction_provider: ContentExtractionProvider,
    ) -> None:
        """Initialize the orchestrator."""

        self._repository = repository
        self._analysis_provider = analysis_provider
        self._search_provider = search_provider
        self._extraction_provider = extraction_provider

    async def create_run(self, input_data: RunInput) -> RunMetadata:
        """Create one queued run."""

        run = RunMetadata(
            source_type=input_data.source_type,
            source_label=input_data.source_label,
        )
        return await self._repository.create_run(run)

    async def process_run(self, run_id: UUID, input_data: RunInput) -> None:
        """Process one queued run."""

        run = RunMetadata(
            id=run_id,
            source_type=input_data.source_type,
            source_label=input_data.source_label,
            status=RunStatus.RUNNING,
        )
        await self._repository.update_run(run)
        await self._repository.append_event(
            RunEvent(run_id=run_id, stage="run", status="started", message="Run started")
        )

        try:
            extracted = await self._resolve_source(input_data)
            document = normalize_text(input_data, extracted["text"], extracted.get("title"))
            await self._repository.save_document(run_id, document)
            await self._repository.append_event(
                RunEvent(run_id=run_id, stage="ingestion", status="completed", message="Document normalized")
            )

            similarity_results = await self._search_provider.search(
                build_similarity_query(document.title, document.blocks)
            )
            await self._repository.append_event(
                RunEvent(
                    run_id=run_id,
                    stage="similarity",
                    status="completed",
                    message="Similarity search completed",
                    agent_name="similarity",
                    model_name="tavily",
                    metadata={"results": similarity_results},
                )
            )

            all_findings: list[AgentFinding] = []
            all_comments: list[Comment] = []
            ai_likelihood_score = 0.0
            for category in (
                AgentCategory.AI_LIKELIHOOD,
                AgentCategory.VALUE,
                AgentCategory.AUDIENCE,
                AgentCategory.EDITORIAL,
                AgentCategory.SYNTHESIS,
            ):
                raw_findings = await self._analysis_provider.analyze_category(
                    category,
                    document.title,
                    document.blocks,
                )
                await self._repository.append_event(
                    RunEvent(
                        run_id=run_id,
                        stage=category.value,
                        status="completed",
                        message=f"{category.value} analysis completed",
                        agent_name=category.value,
                        model_name=getattr(self._analysis_provider, "model_name", "deterministic"),
                    )
                )
                for item in raw_findings:
                    anchor = create_anchor_from_excerpt(document.blocks, str(item.get("excerpt", "")))
                    await self._repository.save_anchor(run_id, anchor)
                    finding = AgentFinding(
                        category=category,
                        agent_name=category.value,
                        anchor_ids=[anchor.id],
                        rationale=str(item.get("rationale", "")),
                        confidence=_coerce_float(item.get("confidence"), 0.5),
                        model_name=getattr(self._analysis_provider, "model_name", "deterministic"),
                        suggestion=str(item.get("suggestion", "")) or None,
                        metadata={"excerpt": str(item.get("excerpt", ""))},
                    )
                    await self._repository.save_finding(run_id, finding)
                    comment = Comment(
                        run_id=run_id,
                        anchor_id=anchor.id,
                        author_type=AuthorType.AGENT,
                        author_label=f"{category.value} agent",
                        category=category,
                        body=finding.rationale,
                        suggestion=finding.suggestion,
                        review_state=ReviewState.UNREVIEWED,
                    )
                    await self._repository.save_comment(comment)
                    all_findings.append(finding)
                    all_comments.append(comment)
                    if category is AgentCategory.AI_LIKELIHOOD:
                        ai_likelihood_score = max(ai_likelihood_score, finding.confidence)

            overall_score = _score_run(similarity_results, ai_likelihood_score, all_findings)
            summary = RunSummary(
                overall_score=overall_score,
                verdict="Worth reading with edits" if overall_score >= 60 else "Needs stronger differentiation",
                value_summary=_pick_summary(all_findings, AgentCategory.VALUE),
                audience_summary=_pick_summary(all_findings, AgentCategory.AUDIENCE),
                novelty_score=max(
                    0.0,
                    1.0
                    - max(
                        (_coerce_float(item.get("score"), 0.0) for item in similarity_results),
                        default=0.0,
                    ),
                ),
                ai_likelihood=ai_likelihood_score,
            )
            await self._repository.save_summary(run_id, summary)

            completed_run = RunMetadata(
                id=run_id,
                source_type=input_data.source_type,
                source_label=input_data.source_label,
                status=RunStatus.COMPLETED,
                created_at=run.created_at,
                updated_at=datetime.now(UTC),
            )
            await self._repository.update_run(completed_run)
            await self._repository.append_event(
                RunEvent(run_id=run_id, stage="run", status="completed", message="Run completed")
            )
        except Exception as error:
            failed_run = RunMetadata(
                id=run_id,
                source_type=input_data.source_type,
                source_label=input_data.source_label,
                status=RunStatus.FAILED,
                created_at=run.created_at,
                updated_at=datetime.now(UTC),
                error_message=str(error),
            )
            await self._repository.update_run(failed_run)
            await self._repository.append_event(
                RunEvent(run_id=run_id, stage="run", status="failed", message=str(error))
            )
            raise

    async def _resolve_source(self, input_data: RunInput) -> dict[str, str]:
        """Resolve one source payload into text and title."""

        if input_data.source_type is SourceType.URL and input_data.url:
            return await self._extraction_provider.extract(input_data.url)
        text = input_data.text or ""
        return {"title": input_data.title or input_data.source_label, "text": text}


def _pick_summary(findings: list[AgentFinding], category: AgentCategory) -> str:
    """Pick one summary string for a category."""

    finding = next((item for item in findings if item.category is category), None)
    return finding.rationale if finding else ""


def _score_run(similarity_results: list[dict[str, object]], ai_likelihood: float, findings: list[AgentFinding]) -> int:
    """Compute a simple editorial score."""

    similarity_penalty = (
        max((_coerce_float(item.get("score"), 0.0) for item in similarity_results), default=0.0) * 25
    )
    ai_penalty = ai_likelihood * 20
    confidence_bonus = (
        sum(
            item.confidence
            for item in findings
            if item.category in (AgentCategory.VALUE, AgentCategory.AUDIENCE)
        )
        * 10
    )
    raw_score = 72 + confidence_bonus - similarity_penalty - ai_penalty
    return max(0, min(100, int(raw_score)))


def _coerce_float(value: object, fallback: float) -> float:
    """Coerce provider values into floats."""

    if isinstance(value, bool):
        return fallback
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback
