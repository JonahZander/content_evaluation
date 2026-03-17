"""Deterministic local providers for tests and no-key development."""

from __future__ import annotations

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
        excerpt = article_text[:80].strip() or "Article opening claim."
        return {
            "findings": [
                {
                    "excerpt": excerpt,
                    "rationale": (
                        "SUPPORTED. Mock research found consistent evidence. "
                        "Sources: https://example.com/mock-1"
                    ),
                    "confidence": 0.75,
                    "suggestion": "Claim appears well-supported. Add citation: https://example.com/mock-1",
                },
                {
                    "excerpt": excerpt[:40] or "Redundancy check.",
                    "rationale": (
                        "MIXED OVERLAP. Some similar posts exist but this article's "
                        "framing adds distinct value."
                    ),
                    "confidence": 0.6,
                    "suggestion": "Differentiate further by citing primary sources.",
                },
            ],
            "summary": "Claims are broadly supported. Article has moderate originality.",
            "metadata": {
                "sources": [
                    "https://example.com/mock-1",
                    "https://example.com/mock-2",
                ],
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "total_tokens": 700,
                },
            },
        }
