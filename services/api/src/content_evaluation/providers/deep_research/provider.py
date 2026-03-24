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

_PROVIDER_SETTINGS: dict[AnalysisProviderFamily, tuple[str, str, str]] = {
    AnalysisProviderFamily.OPENAI: ("openai_model_name", "openai_api_key", "OPENAI_API_KEY"),
    AnalysisProviderFamily.ANTHROPIC: ("anthropic_model_name", "anthropic_api_key", "ANTHROPIC_API_KEY"),
    AnalysisProviderFamily.GEMINI: ("gemini_model_name", "gemini_api_key", "GOOGLE_API_KEY"),
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
        model_attr, api_key_attr, env_key = _PROVIDER_SETTINGS[settings.analysis_provider_family]
        model_name = getattr(settings, model_attr)
        api_key = getattr(settings, api_key_attr)
        if api_key:
            os.environ.setdefault(env_key, api_key)

        if settings.tavily_api_key:
            os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)

        # Light model: used for cheap webpage-summarisation (HTML processing).
        summarization_name = settings.deep_research_summarization_model or model_name
        summarization_model = f"{prefix}:{summarization_name}"
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
        """Run multi-step research and return structured findings."""

        full_brief = f"{brief}\n\nORIGINAL ARTICLE:\n{article_text[:4000]}"
        return await self._invoke_graph(full_brief, article_text)

    async def research(self, prompt: str, article_text: str) -> dict[str, object]:
        """Run prompt-scoped targeted research and return structured findings."""

        full_brief = (
            f"TARGETED FOLLOW-UP RESEARCH\n"
            f"User prompt: {prompt}\n\n"
            f"{article_text[:4000]}"
        )
        parsed = await self._invoke_graph(full_brief, article_text)
        metadata = parsed.get("metadata")
        if isinstance(metadata, dict) and "suggested_research_prompt" not in metadata:
            metadata["suggested_research_prompt"] = prompt
        return parsed

    async def _invoke_graph(self, full_brief: str, article_text: str) -> dict[str, object]:
        """Run the vendored graph and coerce its response into JSON."""

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
            usage_by_model: list[dict[str, int | str]] = []
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
            for model_name, counts in per_model.items():
                if not isinstance(counts, dict):
                    continue
                model_input_t = int(counts.get("input_tokens", 0))
                model_output_t = int(counts.get("output_tokens", 0))
                usage_by_model.append(
                    {
                        "model_name": model_name,
                        "input_tokens": model_input_t,
                        "output_tokens": model_output_t,
                        "total_tokens": model_input_t + model_output_t,
                    }
                )
            parsed["metadata"]["usage"] = {
                "input_tokens": input_t,
                "output_tokens": output_t,
                "total_tokens": input_t + output_t,
            }
            parsed["metadata"]["usage_by_model"] = usage_by_model
        return parsed
