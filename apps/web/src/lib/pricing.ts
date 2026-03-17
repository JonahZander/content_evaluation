import { OPENAI_PRICING_MANIFEST, type OpenAIPricingEntry } from "@/lib/openai-pricing-manifest";

function aliasMatches(alias: string, modelName: string): boolean {
  if (alias.endsWith("*")) {
    return modelName.startsWith(alias.slice(0, -1));
  }
  return modelName === alias;
}

export function resolveOpenAIPricing(modelName: string): OpenAIPricingEntry | null {
  const normalizedName = modelName.trim().toLowerCase();
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

export function formatCost(cost: number): string {
  if (cost < 0.001) return "< $0.001";
  return `$${cost.toFixed(4)}`;
}

export function formatTokens(count: number): string {
  return count.toLocaleString();
}
