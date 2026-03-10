"""Deterministic local providers for tests and no-key development."""

from __future__ import annotations

from content_evaluation.domain.models import AgentCategory, DocumentBlock


class MockSimilaritySearchProvider:
    """Return deterministic similarity results."""

    async def search(self, query: str) -> list[dict[str, object]]:
        """Return synthetic similarity results."""

        return [
            {"title": "Related framing on agentic evaluation", "url": "https://example.com/agentic-evaluation", "score": 0.71},
            {"title": "Editorial review systems for AI content", "url": "https://example.com/editorial-review", "score": 0.64},
            {"title": f"Query echo: {query[:40]}", "url": "https://example.com/query-echo", "score": 0.49},
        ]


class MockContentExtractionProvider:
    """Return synthetic extracted content."""

    async def extract(self, url: str) -> dict[str, str]:
        """Return deterministic content for one URL."""

        title = url.replace("https://", "").replace("http://", "")
        text = (
            f"This article was fetched from {url}. "
            "It discusses how AI-assisted editorial systems review originality, value, and audience fit."
        )
        return {"title": title, "text": text}


class MockAnalysisProvider:
    """Return deterministic findings from local heuristics."""

    async def analyze_category(
        self,
        category: AgentCategory,
        title: str,
        blocks: list[DocumentBlock],
    ) -> list[dict[str, object]]:
        """Return deterministic findings for one category."""

        primary = blocks[0].text if blocks else title
        secondary = blocks[min(1, len(blocks) - 1)].text if blocks else title
        if category is AgentCategory.AI_LIKELIHOOD:
            return [
                {
                    "excerpt": primary[:120],
                    "rationale": "The phrasing is polished and structurally repetitive, which may indicate AI assistance.",
                    "confidence": 0.42,
                    "suggestion": "Add concrete anecdotes or original evidence to reduce generic phrasing.",
                }
            ]
        if category is AgentCategory.VALUE:
            return [
                {
                    "excerpt": primary[:120],
                    "rationale": "The strongest value is practical guidance for editors evaluating whether a post is worth reading.",
                    "confidence": 0.79,
                    "suggestion": "Surface the main takeaway earlier in the introduction.",
                }
            ]
        if category is AgentCategory.AUDIENCE:
            return [
                {
                    "excerpt": secondary[:120],
                    "rationale": "The content appears aimed at editorial, marketing, and AI-operations teams.",
                    "confidence": 0.76,
                    "suggestion": "Name the intended audience directly in the first two paragraphs.",
                }
            ]
        if category is AgentCategory.EDITORIAL:
            return [
                {
                    "excerpt": secondary[:120],
                    "rationale": "This section restates ideas from the introduction without adding new support.",
                    "confidence": 0.67,
                    "suggestion": "Condense or merge this section to tighten the argument.",
                }
            ]
        if category is AgentCategory.SYNTHESIS:
            return [
                {
                    "excerpt": primary[:120],
                    "rationale": "The post feels useful and coherent, but should include sharper evidence and less repetition.",
                    "confidence": 0.83,
                    "suggestion": "Keep the core thesis and trim sections that restate prior points.",
                }
            ]
        return []
