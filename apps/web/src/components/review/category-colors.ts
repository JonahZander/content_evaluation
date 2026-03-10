export const categoryColors: Record<string, string> = {
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
