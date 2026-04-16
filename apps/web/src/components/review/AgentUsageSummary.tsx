import { ArtifactAgentPlanItem, ArtifactAgentResult } from "@/lib/types";
import {
  estimateCost,
  estimateMixedCost,
  formatCost,
  formatTokens,
  type ModelUsageBreakdownEntry,
} from "@/lib/pricing";
import styles from "@/components/ReviewWorkbench.module.css";

interface AgentUsageSummaryProps {
  agentResults: ArtifactAgentResult[];
  agentPlan: ArtifactAgentPlanItem[];
}

interface UsageRow {
  agentId: string;
  displayName: string;
  modelName: string | null;
  inputTokens: number;
  outputTokens: number;
  cost: number | null;
  usageByModel: ModelUsageBreakdownEntry[];
}

function extractUsage(
  metadata: Record<string, unknown>,
): { input_tokens: number; output_tokens: number } | null {
  const usage = metadata.usage;
  if (
    usage !== null &&
    typeof usage === "object" &&
    "input_tokens" in usage &&
    "output_tokens" in usage
  ) {
    const u = usage as { input_tokens: unknown; output_tokens: unknown };
    if (typeof u.input_tokens === "number" && typeof u.output_tokens === "number") {
      return { input_tokens: u.input_tokens, output_tokens: u.output_tokens };
    }
  }
  return null;
}

function extractUsageByModel(metadata: Record<string, unknown>): ModelUsageBreakdownEntry[] {
  const usageByModel = metadata.usage_by_model;
  if (!Array.isArray(usageByModel)) {
    return [];
  }

  return usageByModel.flatMap((entry) => {
    if (entry === null || typeof entry !== "object") {
      return [];
    }

    const candidate = entry as {
      model_name?: unknown;
      input_tokens?: unknown;
      output_tokens?: unknown;
    };

    if (
      typeof candidate.model_name !== "string" ||
      typeof candidate.input_tokens !== "number" ||
      typeof candidate.output_tokens !== "number"
    ) {
      return [];
    }

    return [
      {
        modelName: candidate.model_name,
        inputTokens: candidate.input_tokens,
        outputTokens: candidate.output_tokens,
      },
    ];
  });
}

function renderModelName(modelName: string) {
  return (
    <span title={modelName}>
      {modelName.length > 28 ? `${modelName.slice(0, 26)}…` : modelName}
    </span>
  );
}

export function AgentUsageSummary({ agentResults, agentPlan }: AgentUsageSummaryProps) {
  const planByAgentId = new Map<string, ArtifactAgentPlanItem>(
    agentPlan.map((item) => [item.agent_id, item]),
  );

  const rows: UsageRow[] = [];

  for (const result of agentResults) {
    const usage = extractUsage(result.metadata);
    if (!usage) continue;

    const planItem = planByAgentId.get(result.agent_id);
    const displayName = planItem?.display_name ?? result.agent_id;
    const usageByModel = extractUsageByModel(result.metadata);
    const hasMixedModels = usageByModel.length > 1;
    const modelName = hasMixedModels ? "mixed" : (usageByModel[0]?.modelName ?? planItem?.model_name ?? null);

    const cost =
      hasMixedModels
        ? estimateMixedCost(usageByModel)
        : modelName !== null
          ? estimateCost(modelName, usage.input_tokens, usage.output_tokens)
        : null;

    rows.push({
      agentId: result.agent_id,
      displayName,
      modelName,
      inputTokens: usage.input_tokens,
      outputTokens: usage.output_tokens,
      cost,
      usageByModel,
    });
  }

  if (rows.length === 0) return null;

  const totalInput = rows.reduce((sum, r) => sum + r.inputTokens, 0);
  const totalOutput = rows.reduce((sum, r) => sum + r.outputTokens, 0);
  const hasCosts = rows.some((r) => r.cost !== null);
  const totalCost = hasCosts
    ? rows.reduce((sum, r) => sum + (r.cost ?? 0), 0)
    : null;

  return (
    <div className={styles.usageSummary}>
      <h3 className={styles.sectionTitle}>Token Usage</h3>
      <table className={styles.usageTable}>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Model</th>
            <th className={styles.usageTableNumeric}>In</th>
            <th className={styles.usageTableNumeric}>Out</th>
            <th className={styles.usageTableNumeric}>Est. cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.agentId}>
              <td>{row.displayName}</td>
              <td>
                {row.modelName ? (
                  <div className={styles.usageModelCell}>
                    {renderModelName(row.modelName)}
                    {row.usageByModel.length > 1 ? (
                      <div className={styles.usageModelBreakdown}>
                        {row.usageByModel.map((entry) => {
                          const entryCost = estimateCost(
                            entry.modelName,
                            entry.inputTokens,
                            entry.outputTokens,
                          );
                          return (
                            <div key={entry.modelName} className={styles.usageModelBreakdownRow}>
                              <span className={styles.usageModelBreakdownName} title={entry.modelName}>
                                {entry.modelName}
                              </span>
                              <span className={styles.usageModelBreakdownMetrics}>
                                {formatTokens(entry.inputTokens)} in / {formatTokens(entry.outputTokens)} out
                                {" · "}
                                {entryCost !== null ? formatCost(entryCost) : "—"}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <span className={styles.usageUnknown}>—</span>
                )}
              </td>
              <td className={styles.usageTableNumeric}>{formatTokens(row.inputTokens)}</td>
              <td className={styles.usageTableNumeric}>{formatTokens(row.outputTokens)}</td>
              <td className={styles.usageTableNumeric}>
                {row.cost !== null ? (
                  formatCost(row.cost)
                ) : (
                  <span className={styles.usageUnknown}>—</span>
                )}
              </td>
            </tr>
          ))}
          <tr>
            <td colSpan={2}>Total</td>
            <td className={styles.usageTableNumeric}>{formatTokens(totalInput)}</td>
            <td className={styles.usageTableNumeric}>{formatTokens(totalOutput)}</td>
            <td className={styles.usageTableNumeric}>
              {totalCost !== null ? (
                formatCost(totalCost)
              ) : (
                <span className={styles.usageUnknown}>—</span>
              )}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
