export interface OpenAIPricingEntry {
  inputPerM: number;
  outputPerM: number;
  aliases?: string[];
}

export interface OpenAIPricingManifest {
  source: string;
  lastVerifiedAt: string;
  models: Record<string, OpenAIPricingEntry>;
}

export const OPENAI_PRICING_MANIFEST: OpenAIPricingManifest = {
  source: "https://openai.com/api/pricing/",
  lastVerifiedAt: "2026-03-17",
  models: {
    "gpt-5.4": {
      inputPerM: 2.5,
      outputPerM: 15,
      aliases: ["gpt-5.4-*"],
    },
    "gpt-5": {
      inputPerM: 1.25,
      outputPerM: 10,
      aliases: ["gpt-5-*", "chatgpt-5-latest"],
    },
    "gpt-5-mini": {
      inputPerM: 0.25,
      outputPerM: 2,
      aliases: ["gpt-5-mini-*"],
    },
    "gpt-5-nano": {
      inputPerM: 0.05,
      outputPerM: 0.4,
      aliases: ["gpt-5-nano-*"],
    },
    "gpt-4.1": {
      inputPerM: 2,
      outputPerM: 8,
      aliases: ["gpt-4.1-*"],
    },
    "gpt-4.1-mini": {
      inputPerM: 0.4,
      outputPerM: 1.6,
      aliases: ["gpt-4.1-mini-*"],
    },
    "gpt-4.1-nano": {
      inputPerM: 0.1,
      outputPerM: 0.4,
      aliases: ["gpt-4.1-nano-*"],
    },
  },
};
