/**
 * Hardcoded per-model pricing for cost estimation.
 * Prices are USD per 1 million tokens (input / output).
 * OpenAI entries are sourced from the official models and pricing docs:
 * https://developers.openai.com/api/docs/models
 * https://openai.com/api/pricing/
 * Update this table when provider pricing changes.
 */

interface PricingEntry {
  pattern: RegExp;
  inputPerM: number;
  outputPerM: number;
}

const PRICING: PricingEntry[] = [
  // OpenAI — more specific patterns first
  { pattern: /gpt-5\.4/i,                inputPerM: 2.50,  outputPerM: 15.00 },
  { pattern: /gpt-5-mini/i,             inputPerM: 0.25,  outputPerM: 2.00  },
  { pattern: /gpt-5-nano/i,             inputPerM: 0.05,  outputPerM: 0.40  },
  { pattern: /gpt-4\.1-mini/i,          inputPerM: 0.40,  outputPerM: 1.60  },
  { pattern: /gpt-4\.1(?!-mini)/i,      inputPerM: 2.00,  outputPerM: 8.00  },
  { pattern: /gpt-4o-mini/i,              inputPerM: 0.15,  outputPerM: 0.60  },
  { pattern: /gpt-4o/i,                   inputPerM: 2.50,  outputPerM: 10.00 },
  { pattern: /gpt-4-turbo/i,             inputPerM: 10.00, outputPerM: 30.00 },
  // Anthropic
  { pattern: /claude-3-5-haiku|claude-haiku-4/i,   inputPerM: 0.80,  outputPerM: 4.00  },
  { pattern: /claude-3-5-sonnet|claude-sonnet-4/i, inputPerM: 3.00,  outputPerM: 15.00 },
  { pattern: /claude-3-opus|claude-opus-4/i,        inputPerM: 15.00, outputPerM: 75.00 },
  // Google
  { pattern: /gemini-2\.0-flash/i,  inputPerM: 0.10,  outputPerM: 0.40 },
  { pattern: /gemini-1\.5-flash/i,  inputPerM: 0.075, outputPerM: 0.30 },
  { pattern: /gemini-1\.5-pro/i,    inputPerM: 1.25,  outputPerM: 5.00 },
];

/** Return estimated USD cost, or null if the model is not in the pricing table. */
export function estimateCost(
  modelName: string,
  inputTokens: number,
  outputTokens: number,
): number | null {
  const entry = PRICING.find((e) => e.pattern.test(modelName));
  if (!entry) return null;
  return (
    (inputTokens / 1_000_000) * entry.inputPerM +
    (outputTokens / 1_000_000) * entry.outputPerM
  );
}

/** Format a cost for display. Returns "< $0.001" for sub-cent amounts. */
export function formatCost(cost: number): string {
  if (cost < 0.001) return "< $0.001";
  return `$${cost.toFixed(4)}`;
}

/** Format a token count with thousands separators. */
export function formatTokens(count: number): string {
  return count.toLocaleString();
}
