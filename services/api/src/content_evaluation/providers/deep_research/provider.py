"""LiveDeepResearchProvider — wraps the vendored deep researcher graph."""

from __future__ import annotations

import json
import uuid

from langgraph.checkpoint.memory import MemorySaver

from content_evaluation.providers.deep_research.deep_researcher import deep_researcher_builder


class LiveDeepResearchProvider:
    """Run the vendored deep researcher graph and return structured FindingPayload dicts."""

    model_name = "deep-researcher"

    def __init__(
        self,
        research_model: str = "openai:gpt-4.1-mini",
        max_researcher_iterations: int = 2,
        max_react_tool_calls: int = 5,
        max_concurrent_research_units: int = 2,
    ) -> None:
        """Initialize with cost-limit config."""

        self._research_config: dict[str, object] = {
            "allow_clarification": False,
            "search_api": "tavily",
            "max_researcher_iterations": max_researcher_iterations,
            "max_react_tool_calls": max_react_tool_calls,
            "max_concurrent_research_units": max_concurrent_research_units,
            "research_model": research_model,
            "compression_model": research_model,
            "final_report_model": research_model,
            "summarization_model": research_model,
        }

    async def fact_check(self, brief: str, article_text: str) -> dict[str, object]:
        """Run multi-step research and return structured findings.

        brief + article_text are combined into the research brief and injected
        directly into state, bypassing the write_research_brief LLM node.
        The graph's final_report_generation_prompt outputs structured JSON directly.
        """

        full_brief = f"{brief}\n\nORIGINAL ARTICLE:\n{article_text[:4000]}"
        graph = deep_researcher_builder.compile(checkpointer=MemorySaver())
        config: dict[str, object] = {
            "configurable": {
                "thread_id": str(uuid.uuid4()),
                **self._research_config,
            }
        }
        result = await graph.ainvoke(
            {
                "messages": [{"role": "user", "content": full_brief}],
                "research_brief": full_brief,
            },
            config,
        )
        raw: str = result.get("final_report") or ""

        try:
            parsed: dict[str, object] = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "findings": [
                    {
                        "excerpt": article_text[:80].strip(),
                        "rationale": raw[:500] or "Research completed but output was not valid JSON.",
                        "confidence": 0.5,
                        "suggestion": "Check raw output in metadata.raw_report.",
                    }
                ],
                "summary": "Research completed. Output parsing failed — see metadata.raw_report.",
                "metadata": {"sources": [], "raw_report": raw[:3000]},
            }

        if "metadata" not in parsed:
            parsed["metadata"] = {}
        return parsed
