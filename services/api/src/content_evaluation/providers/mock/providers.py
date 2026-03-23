"""Deterministic local providers for tests and no-key development."""

from __future__ import annotations

from collections.abc import Iterable

from content_evaluation.domain.models import ArtifactBlock, ContentFormat, ExtractedContent, ProviderRoute


class MockSimilaritySearchProvider:
    """Return deterministic similarity results."""

    async def search(self, query: str) -> list[dict[str, object]]:
        """Return synthetic similarity results."""

        return [
            {
                "title": "Related framing on agentic evaluation",
                "url": "https://example.com/agentic-evaluation",
                "score": 0.71,
            },
            {
                "title": "Editorial review systems for AI content",
                "url": "https://example.com/editorial-review",
                "score": 0.64,
            },
            {
                "title": f"Query echo: {query[:40]}",
                "url": "https://example.com/query-echo",
                "score": 0.49,
            },
        ]


class MockContentExtractionProvider:
    """Return synthetic extracted content."""

    async def extract(self, url: str) -> ExtractedContent:
        """Return deterministic content for one URL."""

        title = url.replace("https://", "").replace("http://", "")
        text = (
            f"This article was fetched from {url}. "
            "It discusses how AI-assisted editorial systems review originality, value, and audience fit."
        )
        return ExtractedContent(
            title=title,
            content=text,
            content_format=ContentFormat.PLAIN_TEXT,
            metadata={"provider_name": "mock-extract", "content_format": ContentFormat.PLAIN_TEXT.value},
        )


class MockAnalysisProvider:
    """Return deterministic findings from local heuristics."""

    model_name = "mock-analysis"

    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
        route: ProviderRoute | None = None,
    ) -> dict[str, object]:
        """Return deterministic JSON for one analysis agent."""

        del instruction
        del route
        primary = blocks[0].text if blocks else title
        secondary = blocks[min(1, len(blocks) - 1)].text if blocks else title
        result: dict[str, object] = {"findings": []}
        findings = result["findings"]
        assert isinstance(findings, list)
        if agent_id == "ai_likelihood":
            findings.append(
                {
                    "excerpt": primary[:120],
                    "rationale": (
                        "The phrasing is polished and structurally repetitive, which may indicate AI assistance."
                    ),
                    "confidence": 0.42,
                    "suggestion": "Add concrete anecdotes or original evidence to reduce generic phrasing.",
                }
            )
        elif agent_id == "value":
            findings.append(
                {
                    "excerpt": primary[:120],
                    "rationale": (
                        "The strongest value is practical guidance for editors "
                        "evaluating whether a post is worth reading."
                    ),
                    "confidence": 0.79,
                    "suggestion": "Surface the main takeaway earlier in the introduction.",
                }
            )
        elif agent_id == "audience":
            findings.append(
                {
                    "excerpt": secondary[:120],
                    "rationale": "The content appears aimed at editorial, marketing, and AI-operations teams.",
                    "confidence": 0.76,
                    "suggestion": "Name the intended audience directly in the first two paragraphs.",
                }
            )
        elif agent_id == "editorial":
            findings.append(
                {
                    "excerpt": secondary[:120],
                    "rationale": "This section restates ideas from the introduction without adding new support.",
                    "confidence": 0.67,
                    "suggestion": "Condense or merge this section to tighten the argument.",
                }
            )
        elif agent_id == "synthesis":
            context_summary = ", ".join(sorted((context or {}).keys()))
            findings.append(
                {
                    "excerpt": primary[:120],
                    "rationale": (
                        "The post feels useful and coherent, but should include "
                        "sharper evidence and less repetition."
                    ),
                    "confidence": 0.83,
                    "suggestion": "Keep the core thesis and trim sections that restate prior points.",
                }
            )
            result["summary"] = f"Synthesized from: {context_summary}" if context_summary else "Synthesis complete"
        result["usage"] = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return result

    def resolve_model_name(self, route: ProviderRoute | None = None) -> str:
        """Return the configured mock model name."""

        del route
        return self.model_name


class MockDeepResearchProvider:
    """Return deterministic fact-check findings for tests and no-key development."""

    model_name = "mock-deep-research"

    async def fact_check(self, brief: str, article_text: str) -> dict[str, object]:
        """Return synthetic fact-check findings."""

        del brief
        compact_article_text = " ".join(article_text.split())
        word_count = len(compact_article_text.split())
        reading_time_minutes = max(1, (word_count + 199) // 200)
        primary_excerpt = compact_article_text[:96].strip() or "Article opening claim."
        secondary_excerpt = compact_article_text[96:192].strip() or compact_article_text[:96].strip() or primary_excerpt
        related_post_links = [
            "https://example.com/agentic-evaluation",
            "https://example.com/editorial-review",
        ]
        official_source_links = [
            "https://example.com/official-source-1",
            "https://example.com/official-source-2",
        ]
        claim_findings = [
            _mock_claim_entry(
                claim_text=primary_excerpt,
                verdict="SUPPORTED",
                evidence_summary="Supported by consistent reporting across the linked sources.",
                source_links=[official_source_links[0]],
                anchor_excerpt=primary_excerpt,
                confidence=0.82,
                suggestion="Add an inline citation to the primary supporting source.",
                value_add="Useful because it ties the article to a concrete editorial workflow claim.",
                official_source_links=[official_source_links[0]],
                related_post_links=[related_post_links[0]],
            ),
            _mock_claim_entry(
                claim_text=secondary_excerpt,
                verdict="MIXED",
                evidence_summary="The broader framing is plausible, but the article would benefit from a more specific source.",
                source_links=[official_source_links[1]],
                anchor_excerpt=secondary_excerpt,
                confidence=0.68,
                suggestion="Name the most relevant primary source directly in this section.",
                value_add="Adds value by clarifying where the article should lean on original reporting versus interpretation.",
                official_source_links=[official_source_links[1]],
                related_post_links=[related_post_links[1]],
            ),
        ]
        overlap_items = [
            {
                "title": "Related framing on agentic evaluation",
                "url": related_post_links[0],
                "overlap_note": "Moderate overlap in framing, but the article still adds useful editorial workflow detail.",
                "score": 0.58,
            },
            {
                "title": "Editorial review systems for AI content",
                "url": related_post_links[1],
                "overlap_note": "Low overlap. Similar topic area with a different angle and audience.",
                "score": 0.24,
            },
        ]
        main_claims = [
            {
                "claim_text": item["claim_text"],
                "verdict": item["verdict"],
                "evidence_summary": item["evidence_summary"],
                "source_links": list(item["source_links"]),
                "anchor_quote": item["anchor_excerpt"],
                "value_add": item["value_add"],
                "official_source_links": list(item["official_source_links"]),
                "related_post_links": list(item["related_post_links"]),
            }
            for item in claim_findings
        ]
        return {
            "claim_findings": claim_findings,
            "main_claims": main_claims,
            "findings": [
                {
                    "excerpt": item["anchor_excerpt"],
                    "rationale": item["evidence_summary"],
                    "confidence": item["confidence"],
                    "suggestion": item["suggestion"],
                    "sources": list(item["source_links"]),
                    "metadata": {
                        "claim_text": item["claim_text"],
                        "verdict": item["verdict"],
                        "evidence_summary": item["evidence_summary"],
                        "value_add": item["value_add"],
                        "official_source_links": list(item["official_source_links"]),
                        "related_post_links": list(item["related_post_links"]),
                    },
                }
                for item in claim_findings
            ],
            "overlap_items": overlap_items,
            "summary": "Claims are broadly supported and the article still brings a reasonably differentiated angle.",
            "research_summary": "Claims are broadly supported, and overlap research suggests the piece still adds useful editorial workflow detail.",
            "tl_dr": "The article is directionally sound, useful, and differentiated enough to keep with better source support.",
            "metadata": {
                "sources": [
                    "https://example.com/mock-1",
                    "https://example.com/mock-2",
                ],
                "official_source_links": official_source_links,
                "related_post_links": related_post_links,
                "audience": "Editorial, content strategy, and AI operations teams",
                "article_format": "analysis",
                "word_count": word_count,
                "estimated_reading_time_minutes": reading_time_minutes,
                "structural_completeness": {
                    "has_intro": True,
                    "has_headings": "##" in article_text,
                    "has_conclusion": compact_article_text.endswith("."),
                },
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "total_tokens": 700,
                },
            },
        }


def _mock_claim_entry(
    *,
    claim_text: str,
    verdict: str,
    evidence_summary: str,
    source_links: Iterable[str],
    anchor_excerpt: str,
    confidence: float,
    suggestion: str,
    value_add: str,
    official_source_links: Iterable[str],
    related_post_links: Iterable[str],
) -> dict[str, object]:
    """Build one deterministic mock claim entry."""

    return {
        "claim_text": claim_text,
        "verdict": verdict,
        "evidence_summary": evidence_summary,
        "source_links": list(source_links),
        "anchor_excerpt": anchor_excerpt,
        "confidence": confidence,
        "suggestion": suggestion,
        "value_add": value_add,
        "official_source_links": list(official_source_links),
        "related_post_links": list(related_post_links),
    }
