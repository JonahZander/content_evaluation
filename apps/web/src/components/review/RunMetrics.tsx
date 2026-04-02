import styles from "@/components/ReviewWorkbench.module.css";
import type { ArtifactSummary } from "@/lib/types";

interface RunMetricsProps {
  summary: ArtifactSummary | null;
}

export function RunMetrics({ summary }: RunMetricsProps) {
  function formatSubScore(score: number | null | undefined): string {
    if (score === null || score === undefined) {
      return "—";
    }
    return `${Math.round(score * 100)}%`;
  }

  function formatCount(count: number | null | undefined): string {
    if (count === null || count === undefined || Number.isNaN(count) || count <= 0) {
      return "—";
    }
    return new Intl.NumberFormat("en-US").format(count);
  }

  const wordCountLabel = formatCount(summary?.word_count);
  const readingTimeLabel =
    summary?.estimated_reading_time_minutes && summary.estimated_reading_time_minutes > 0
      ? `${summary.estimated_reading_time_minutes} min read`
      : "Pending";

  const overallScore = summary?.overall_score != null ? `${summary.overall_score}%` : "—";
  const verdict = summary?.verdict ?? null;

  return (
    <section className={styles.metrics}>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Overall score</div>
        <div className={styles.metricValue}>{overallScore}</div>
        {verdict && <div className={styles.metricValueCompact}>{verdict}</div>}
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>TL;DR</div>
        <div className={styles.metricValueCompact}>{summary?.tl_dr || "Pending"}</div>
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Article length</div>
        <div className={styles.metricValueCompact}>
          {wordCountLabel === "—" ? "Pending" : `${wordCountLabel} words`}
          <br />
          {readingTimeLabel}
        </div>
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Novelty</div>
        <div className={styles.metricValue}>{formatSubScore(summary?.novelty_score)}</div>
      </article>
      <article className={styles.metricCard}>
        <div className={styles.metricLabel}>Human voice</div>
        <div className={styles.metricValue}>{formatSubScore(summary?.ai_likelihood)}</div>
      </article>
    </section>
  );
}
