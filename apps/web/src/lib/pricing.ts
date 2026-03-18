import { OPENAI_PRICING_MANIFEST, type OpenAIPricingEntry } from "@/lib/openai-pricing-manifest";

export interface ModelUsageBreakdownEntry {
  modelName: string;
  inputTokens: number;
  outputTokens: number;
}

function normalizePricedModelName(modelName: string): string {
  const normalized = modelName.trim().toLowerCase();
  const segments = normalized.split(":");
  if (segments.length === 2) {
    const [provider, name] = segments;
    if (provider === "openai" || provider === "anthropic" || provider === "google" || provider === "google_genai") {
      return name;
    }
  }
  return normalized;
}

function aliasMatches(alias: string, modelName: string): boolean {
  if (alias.endsWith("*")) {
    return modelName.startsWith(alias.slice(0, -1));
  }
  return modelName === alias;
}

export function resolveOpenAIPricing(modelName: string): OpenAIPricingEntry | null {
  const normalizedName = normalizePricedModelName(modelName);
  const direct = OPENAI_PRICING_MANIFEST.models[normalizedName];
  if (direct) {
    return direct;
  }

  const aliasMatchesByLength = Object.values(OPENAI_PRICING_MANIFEST.models)
    .flatMap((entry) =>
      (entry.aliases ?? []).map((alias) => ({
        alias: alias.toLowerCase(),
        entry,
      })),
    )
    .filter(({ alias }) => aliasMatches(alias, normalizedName))
    .sort((left, right) => right.alias.length - left.alias.length);

  return aliasMatchesByLength[0]?.entry ?? null;
}

export function estimateCost(
  modelName: string,
  inputTokens: number,
  outputTokens: number,
): number | null {
  const entry = resolveOpenAIPricing(modelName);
  if (entry === null) {
    return null;
  }
  return (
    (inputTokens / 1_000_000) * entry.inputPerM +
    (outputTokens / 1_000_000) * entry.outputPerM
  );
}

export function estimateMixedCost(entries: ModelUsageBreakdownEntry[]): number | null {
  let total = 0;
  let hasKnownCost = false;

  for (const entry of entries) {
    const cost = estimateCost(entry.modelName, entry.inputTokens, entry.outputTokens);
    if (cost === null) {
      continue;
    }
    total += cost;
    hasKnownCost = true;
  }

  return hasKnownCost ? total : null;
}

export function formatCost(cost: number): string {
  if (cost < 0.001) return "< $0.001";
  return `$${cost.toFixed(4)}`;
}

export function formatTokens(count: number): string {
  return count.toLocaleString();
}
