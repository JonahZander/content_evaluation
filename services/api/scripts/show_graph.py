#!/usr/bin/env python
"""Print Mermaid diagrams for all LangGraph graphs in this project.

Usage (from services/api/):
    uv run python scripts/show_graph.py

Outputs Mermaid source for:
  1. Main orchestration graph — all agents including fact_check
  2. Deep research graph (supervisor + researchers)
  3. Deep research graph with subgraphs expanded (xray=True)

Paste any block into https://mermaid.live to view it visually.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")  # ensure src/ is on the path when run directly


def _print_section(title: str, mermaid: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)
    print()
    print(mermaid)
    print()


def show_orchestration_graph() -> None:
    """Build the main orchestration graph with every registered agent."""
    from content_evaluation.agents.registry import list_agent_definitions
    from content_evaluation.domain.models import OrchestratorBackend, RuntimeMode
    from content_evaluation.providers.mock.providers import (
        MockAnalysisProvider,
        MockContentExtractionProvider,
        MockSimilaritySearchProvider,
    )
    from content_evaluation.repositories.in_memory import InMemoryRunRepository
    from content_evaluation.services.orchestration import RunOrchestrator

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
    )

    all_agent_ids = [d.agent_id for d in list_agent_definitions()]
    compiled = orchestrator._build_langgraph_app(all_agent_ids)  # type: ignore[attr-defined]

    _print_section(
        "MAIN ORCHESTRATION GRAPH  (all agents)",
        compiled.get_graph().draw_mermaid(),
    )


def show_deep_research_graph() -> None:
    """Compile and render the deep research graph."""
    from langgraph.checkpoint.memory import MemorySaver

    from content_evaluation.providers.deep_research.deep_researcher import (
        deep_researcher_builder,
    )

    compiled = deep_researcher_builder.compile(checkpointer=MemorySaver())

    _print_section(
        "DEEP RESEARCH GRAPH  (top-level nodes)",
        compiled.get_graph().draw_mermaid(),
    )

    _print_section(
        "DEEP RESEARCH GRAPH  (subgraphs expanded, xray=True)",
        compiled.get_graph(xray=True).draw_mermaid(),
    )


if __name__ == "__main__":
    print("Rendering LangGraph graphs as Mermaid diagrams.")
    print("Paste any diagram block into https://mermaid.live to visualise.")

    show_orchestration_graph()

    try:
        show_deep_research_graph()
    except Exception as exc:  # noqa: BLE001
        print()
        print(f"[deep research graph] Could not render: {exc}")
        print("(This graph may require optional model dependencies.)")
