import { render, screen } from "@testing-library/react";

import { AgentUsageSummary } from "@/components/review/AgentUsageSummary";
import type { ArtifactAgentPlanItem, ArtifactAgentResult } from "@/lib/types";

function hasExactText(text: string) {
  return (_content: string, node: Element | null) => node?.textContent === text;
}

describe("AgentUsageSummary", () => {
  it("shows mixed-model deep research rows with a per-model cost breakdown", () => {
    const agentPlan: ArtifactAgentPlanItem[] = [
      {
        agent_id: "fact_check",
        display_name: "Fact Check",
        category: "fact_check",
        depends_on: [],
        provider_kind: "deep_research",
        execution_mode: "multi_step",
        instruction_file: "fact_check/research_brief.md",
        status: "completed",
        model_name: "deep-researcher",
      },
      {
        agent_id: "ai_likelihood",
        display_name: "AI Likelihood",
        category: "ai_likelihood",
        depends_on: [],
        provider_kind: "analysis",
        execution_mode: "single_turn",
        instruction_file: "ai_likelihood.md",
        status: "completed",
        model_name: "gpt-5.4-nano-2026-03-17",
      },
    ];

    const agentResults: ArtifactAgentResult[] = [
      {
        agent_id: "fact_check",
        category: "fact_check",
        status: "completed",
        findings: [],
        summary: "Checked",
        raw_output: {},
        metadata: {
          usage: {
            input_tokens: 420_000,
            output_tokens: 45_000,
            total_tokens: 465_000,
          },
          usage_by_model: [
            {
              model_name: "openai:gpt-5.4-nano-2026-03-17",
              input_tokens: 400_000,
              output_tokens: 40_000,
              total_tokens: 440_000,
            },
            {
              model_name: "openai:gpt-5.4-2026-03-17",
              input_tokens: 20_000,
              output_tokens: 5_000,
              total_tokens: 25_000,
            },
          ],
        },
      },
      {
        agent_id: "ai_likelihood",
        category: "ai_likelihood",
        status: "completed",
        findings: [],
        summary: "Likely human",
        raw_output: {},
        metadata: {
          usage: {
            input_tokens: 1_000_000,
            output_tokens: 1_000_000,
            total_tokens: 2_000_000,
          },
        },
      },
    ];

    render(<AgentUsageSummary agentResults={agentResults} agentPlan={agentPlan} />);

    expect(screen.getByText("mixed")).toBeInTheDocument();
    expect(screen.getByText("openai:gpt-5.4-nano-2026-03-17")).toBeInTheDocument();
    expect(screen.getByText("openai:gpt-5.4-2026-03-17")).toBeInTheDocument();
    expect(
      screen.getByText(hasExactText("400,000 in / 40,000 out · $1.6000")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(hasExactText("20,000 in / 5,000 out · $0.1250")),
    ).toBeInTheDocument();
    expect(screen.getByText("$1.7250")).toBeInTheDocument();
    expect(screen.getByText("$17.5000")).toBeInTheDocument();
    expect(screen.getByText("$19.2250")).toBeInTheDocument();
  });
});
