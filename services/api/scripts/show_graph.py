#!/usr/bin/env python
"""Save LangGraph graphs as PNG files using mmdc (mermaid-cli via npx).

Usage (from services/api/):
    uv run python scripts/show_graph.py

Writes three files to /tmp/:
  graph_orchestration.png      — main pipeline with all agents
  graph_deep_research.png      — deep research top-level nodes
  graph_deep_research_xray.png — deep research with subgraphs expanded
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

OUTPUT_DIR = Path(__file__).parent.parent / "graphs"


def mermaid_to_png(mermaid: str, output_path: Path) -> Path:
    """Render a Mermaid diagram string to a PNG file using npx mmdc."""
    with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False) as f:
        f.write(mermaid)
        mmd_path = f.name
    subprocess.run(
        ["npx", "--yes", "@mermaid-js/mermaid-cli", "-i", mmd_path, "-o", str(output_path)],
        check=True,
        capture_output=True,
    )
    return output_path


def render_orchestration_graph() -> Path:
    from content_evaluation.agents.registry import list_agent_definitions
    from content_evaluation.domain.models import OrchestratorBackend, RuntimeMode
    from content_evaluation.providers.mock.providers import (
        MockAnalysisProvider,
        MockContentExtractionProvider,
        MockSimilaritySearchProvider,
    )
    from content_evaluation.repositories.in_memory import InMemoryRunRepository
    from content_evaluation.services.orchestration import RunOrchestrator

    orchestrator = RunOrchestrator(
        InMemoryRunRepository(),
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
    )
    all_agent_ids = [d.agent_id for d in list_agent_definitions()]
    compiled = orchestrator._build_langgraph_app(all_agent_ids)  # type: ignore[attr-defined]
    mermaid = compiled.get_graph().draw_mermaid()
    return mermaid_to_png(mermaid, OUTPUT_DIR / "graph_orchestration.png")


def render_deep_research_graphs() -> tuple[Path, Path]:
    from langgraph.checkpoint.memory import MemorySaver

    from content_evaluation.providers.deep_research.deep_researcher import deep_researcher_builder

    compiled = deep_researcher_builder.compile(checkpointer=MemorySaver())
    top = mermaid_to_png(
        compiled.get_graph().draw_mermaid(),
        OUTPUT_DIR / "graph_deep_research.png",
    )
    xray = mermaid_to_png(
        compiled.get_graph(xray=True).draw_mermaid(),
        OUTPUT_DIR / "graph_deep_research_xray.png",
    )
    return top, xray


if __name__ == "__main__":
    print("Generating graphs...")

    path = render_orchestration_graph()
    print(f"  {path}")

    try:
        top, xray = render_deep_research_graphs()
        print(f"  {top}")
        print(f"  {xray}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [deep research] Could not render: {exc}")
