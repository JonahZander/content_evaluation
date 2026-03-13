export const categoryColors: Record<string, string> = {
  fact_check: "var(--sky)",
  similarity: "var(--amber)",
  ai_likelihood: "var(--vermilion)",
  value: "var(--teal)",
  audience: "var(--cobalt)",
  editorial: "var(--olive)",
  synthesis: "var(--ink)",
  human: "var(--human)",
};

export function colorForCategory(category: string): string {
  return categoryColors[category] ?? "var(--ink)";
}
