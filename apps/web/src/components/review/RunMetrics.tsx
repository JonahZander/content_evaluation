import styles from "@/components/ReviewWorkbench.module.css";
import type { ArtifactSummary } from "@/lib/types";

interface RunMetricsProps {
  summary: ArtifactSummary | null;
}

export function RunMetrics({ summary }: RunMetricsProps) {
  const formatScore = (score: number | null | undefined): string => {
    if (score === null || score === undefined) {
      return "—";
    }
    return `${Math.round(score * 100)}%`;
  };

  return (
    <section className={styles.metrics}>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Novelty</div>
        <div className={styles.metricValue}>{formatScore(summary?.novelty_score)}</div>
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>AI likelihood</div>
        <div className={styles.metricValue}>{formatScore(summary?.ai_likelihood)}</div>
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Value</div>
        <div className={styles.metricValue}>{summary?.value_summary ?? "Pending"}</div>
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Audience</div>
        <div className={styles.metricValue}>{summary?.audience_summary ?? "Pending"}</div>
      </article>
    </section>
  );
}
