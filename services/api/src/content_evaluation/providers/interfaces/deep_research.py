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
            {"findings": [{"excerpt": str, "rationale": str,
                           "confidence": float, "suggestion": str}],
             "summary": str,
             "metadata": {"sources": [str]}}
        """
        ...
