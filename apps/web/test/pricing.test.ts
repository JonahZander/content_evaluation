import { describe, expect, it } from "vitest";

import { estimateCost, resolveOpenAIPricing } from "@/lib/pricing";

describe("pricing", () => {
  it("matches GPT-5.4 pricing from the official docs", () => {
    expect(estimateCost("gpt-5.4", 1_000_000, 1_000_000)).toBe(17.5);
  });

  it("matches GPT-5 mini pricing from the official docs", () => {
    expect(estimateCost("gpt-5-mini-2025-08-07", 1_000_000, 1_000_000)).toBe(2.25);
  });

  it("matches GPT-5 nano pricing from the official docs", () => {
    expect(estimateCost("gpt-5-nano", 1_000_000, 1_000_000)).toBe(0.45);
  });

  it("matches GPT-4.1 mini pricing", () => {
    expect(estimateCost("gpt-4.1-mini", 1_000_000, 1_000_000)).toBe(2.0);
  });

  it("resolves alias model names conservatively", () => {
    expect(resolveOpenAIPricing("chatgpt-5-latest")).toEqual(
      expect.objectContaining({ inputPerM: 1.25, outputPerM: 10 }),
    );
  });

  it("returns null for unknown models", () => {
    expect(estimateCost("unknown-model", 10, 10)).toBeNull();
  });
});
