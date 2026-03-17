"""LiveDeepResearchProvider — wraps the vendored deep researcher graph."""

from __future__ import annotations

import json
import os
import uuid

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langgraph.checkpoint.memory import MemorySaver

from content_evaluation.config import Settings
from content_evaluation.domain.models import AnalysisProviderFamily
from content_evaluation.providers.deep_research.deep_researcher import deep_researcher_builder

_PROVIDER_MODEL_PREFIX: dict[AnalysisProviderFamily, str] = {
    AnalysisProviderFamily.OPENAI: "openai",
    AnalysisProviderFamily.ANTHROPIC: "anthropic",
    AnalysisProviderFamily.GEMINI: "google_genai",
}


class LiveDeepResearchProvider:
    """Run the vendored deep researcher graph and return structured FindingPayload dicts."""

    model_name = "deep-researcher"

    def __init__(
        self,
        settings: Settings,
        max_researcher_iterations: int = 2,
        max_react_tool_calls: int = 5,
        max_concurrent_research_units: int = 2,
    ) -> None:
        """Initialize from project Settings so model and API keys match the rest of the app.

        The vendored graph reads API keys via os.getenv() at call time. pydantic-settings
        loads values from .env into Python objects but does not export them to the OS
        environment. We explicitly export them here so the graph can find them.
        """

        # Derive model string from the same provider family the rest of the app uses.
        prefix = _PROVIDER_MODEL_PREFIX[settings.analysis_provider_family]
        if settings.analysis_provider_family is AnalysisProviderFamily.OPENAI:
            model_name = settings.openai_model_name
            if settings.openai_api_key:
                os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
        elif settings.analysis_provider_family is AnalysisProviderFamily.ANTHROPIC:
            model_name = settings.anthropic_model_name
            if settings.anthropic_api_key:
                os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
        else:
            model_name = settings.gemini_model_name
            if settings.gemini_api_key:
                os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)

        if settings.tavily_api_key:
            os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)

        # Light model: used for cheap webpage-summarisation (HTML processing).
        summarization_model = f"{prefix}:{model_name}"
        # Heavy model: used for supervisor reasoning, researcher agents, compression,
        # and final JSON synthesis. Falls back to the same model when not separately
        # configured via CONTENT_EVAL_DEEP_RESEARCH_MODEL_NAME.
        heavy_name = settings.deep_research_model_name or model_name
        heavy_model = f"{prefix}:{heavy_name}"

        self._research_config: dict[str, object] = {
            "allow_clarification": False,
            "search_api": "tavily",
            "max_researcher_iterations": max_researcher_iterations,
            "max_react_tool_calls": max_react_tool_calls,
            "max_concurrent_research_units": max_concurrent_research_units,
            "research_model": heavy_model,
            "compression_model": heavy_model,
            "final_report_model": heavy_model,
            "summarization_model": summarization_model,
        }

    async def fact_check(self, brief: str, article_text: str) -> dict[str, object]:
        """Run multi-step research and return structured findings.

        brief + article_text are combined into the research brief and injected
        directly into state, bypassing the write_research_brief LLM node.
        The graph's final_report_generation_prompt outputs structured JSON directly.
        """

        full_brief = f"{brief}\n\nORIGINAL ARTICLE:\n{article_text[:4000]}"
        graph = deep_researcher_builder.compile(checkpointer=MemorySaver())
        usage_handler = UsageMetadataCallbackHandler()
        config: dict[str, object] = {
            "configurable": {
                "thread_id": str(uuid.uuid4()),
                **self._research_config,
            },
            "callbacks": [usage_handler],
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

        if "metadata" not in parsed or not isinstance(parsed["metadata"], dict):
            parsed["metadata"] = {}
        per_model = usage_handler.usage_metadata  # {model_name: {token_counts}}
        if per_model:
            input_t = sum(
                int(counts.get("input_tokens", 0))
                for counts in per_model.values()
                if isinstance(counts, dict)
            )
            output_t = sum(
                int(counts.get("output_tokens", 0))
                for counts in per_model.values()
                if isinstance(counts, dict)
            )
            parsed["metadata"]["usage"] = {
                "input_tokens": input_t,
                "output_tokens": output_t,
                "total_tokens": input_t + output_t,
            }
        return parsed
