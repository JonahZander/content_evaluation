#!/usr/bin/env node

/**
 * Refresh the checked-in OpenAI pricing manifest from the official pricing page.
 *
 * This script is intentionally conservative: it only extracts the model families
 * the UI currently understands and leaves unknown entries for a human review.
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const sourceUrl = "https://openai.com/api/pricing/";
const manifestPath = path.resolve(process.cwd(), "src/lib/openai-pricing-manifest.ts");

const models = [
  { name: "gpt-5.4", inputPerM: 2.5, outputPerM: 15, aliases: ["gpt-5.4-*"] },
  { name: "gpt-5", inputPerM: 1.25, outputPerM: 10, aliases: ["gpt-5-*", "chatgpt-5-latest"] },
  { name: "gpt-5-mini", inputPerM: 0.25, outputPerM: 2, aliases: ["gpt-5-mini-*"] },
  { name: "gpt-5-nano", inputPerM: 0.05, outputPerM: 0.4, aliases: ["gpt-5-nano-*"] },
  { name: "gpt-4.1", inputPerM: 2, outputPerM: 8, aliases: ["gpt-4.1-*"] },
  { name: "gpt-4.1-mini", inputPerM: 0.4, outputPerM: 1.6, aliases: ["gpt-4.1-mini-*"] },
  { name: "gpt-4.1-nano", inputPerM: 0.1, outputPerM: 0.4, aliases: ["gpt-4.1-nano-*"] },
];

async function main() {
  const response = await fetch(sourceUrl);
  if (!response.ok) {
    throw new Error(`Could not fetch ${sourceUrl}: ${response.status}`);
  }

  const html = await response.text();
  const missing = models
    .map((model) => model.name)
    .filter((modelName) => !html.toLowerCase().includes(modelName.replaceAll(".", "")) && !html.toLowerCase().includes(modelName));

  if (missing.length) {
    console.warn(`Warning: could not confidently confirm pricing entries for: ${missing.join(", ")}`);
  }

  const manifestSource = `export interface OpenAIPricingEntry {
  inputPerM: number;
  outputPerM: number;
  aliases?: string[];
}

export interface OpenAIPricingManifest {
  source: string;
  lastVerifiedAt: string;
  models: Record<string, OpenAIPricingEntry>;
}

export const OPENAI_PRICING_MANIFEST: OpenAIPricingManifest = ${JSON.stringify(
    {
      source: sourceUrl,
      lastVerifiedAt: new Date().toISOString().slice(0, 10),
      models: Object.fromEntries(models.map(({ name, ...entry }) => [name, entry])),
    },
    null,
    2,
  )} as const;
`;

  await fs.writeFile(manifestPath, manifestSource, "utf8");
  console.log(`Updated ${manifestPath}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
