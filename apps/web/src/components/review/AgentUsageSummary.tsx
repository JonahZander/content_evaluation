import { ArtifactAgentPlanItem, ArtifactAgentResult } from "@/lib/types";
import { estimateCost, formatCost, formatTokens } from "@/lib/pricing";
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
    const modelName = planItem?.model_name ?? null;

    const cost =
      modelName !== null
        ? estimateCost(modelName, usage.input_tokens, usage.output_tokens)
        : null;

    rows.push({
      agentId: result.agent_id,
      displayName,
      modelName,
      inputTokens: usage.input_tokens,
      outputTokens: usage.output_tokens,
      cost,
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
                {row.modelName !== null ? (
                  row.modelName
                ) : (
                  <span className={styles.usageUnknown}>unknown</span>
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
