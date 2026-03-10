import styles from "@/components/ReviewWorkbench.module.css";
import type { RunSummary } from "@/lib/types";

interface RunMetricsProps {
  summary: RunSummary | null;
}

export function RunMetrics({ summary }: RunMetricsProps) {
  return (
    <section className={styles.metrics}>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Novelty</div>
        <div className={styles.metricValue}>{Math.round((summary?.novelty_score ?? 0) * 100)}%</div>
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>AI likelihood</div>
        <div className={styles.metricValue}>{Math.round((summary?.ai_likelihood ?? 0) * 100)}%</div>
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
