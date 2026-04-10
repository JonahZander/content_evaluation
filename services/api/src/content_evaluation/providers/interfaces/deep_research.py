"""Deep research provider interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DeepResearchProvider(Protocol):
    """Run multi-step web research and return structured JSON findings directly."""

    model_name: str

    async def fact_check(
        self,
        brief: str,
        article_text: str,
    ) -> dict[str, object]:
        """Research and fact-check article claims.

        brief: the research task (instruction + article metadata)
        article_text: full article text for excerpt quoting

        Returns:
            {
              "claim_findings": [{
                "claim_text": str,
                "verdict": str,
                "evidence_summary": str,
                "source_links": [str],
                "anchor_excerpt": str,
                "confidence": float,
                "article_cited_links_checked": [{
                  "url": str,
                  "supports_claim": str,
                  "note": str,
                }],
              }],
              "overlap_items": [{"title": str, "url": str, "overlap_note": str}],
              "research_summary": str,
              "summary": str,
              "metadata": {"sources": [str]}
            }
        """
        ...

    async def research(
        self,
        prompt: str,
        article_text: str,
    ) -> dict[str, object]:
        """Run targeted follow-up research for one prompt-scoped question."""
        ...
