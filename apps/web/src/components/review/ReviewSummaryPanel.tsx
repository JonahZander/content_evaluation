import styles from "@/components/ReviewWorkbench.module.css";
import type { ArtifactReviewSummary } from "@/lib/types";

interface ReviewSummaryPanelProps {
  reviewSummary: ArtifactReviewSummary | null;
}

export function ReviewSummaryPanel({ reviewSummary }: ReviewSummaryPanelProps) {
  if (reviewSummary === null) {
    return null;
  }

  const hasOverlapItems = reviewSummary.overlap_items.length > 0;

  return (
    <section className={styles.reviewSummaryPanel} data-testid="review-summary-panel">
      <div>
        <h2 className={styles.sectionTitle}>Review summary</h2>
        <div className={styles.reviewSummaryGrid}>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Content summary</div>
            <p className={styles.reviewSummaryText}>
              {reviewSummary.content_summary || "Pending"}
            </p>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Research summary</div>
            <p className={styles.reviewSummaryText}>
              {reviewSummary.research_summary || "Pending"}
            </p>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Audience</div>
            <p className={styles.reviewSummaryText}>
              {reviewSummary.inferred_audience || "Pending"}
            </p>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Overlap research</div>
            {hasOverlapItems ? (
              <ul className={styles.reviewSummaryLinks}>
                {reviewSummary.overlap_items.map((item) => (
                  <li key={`${item.url}-${item.title}`}>
                    <a className={styles.sourceLink} href={item.url} target="_blank" rel="noreferrer">
                      {item.title}
                    </a>
                    <div className={styles.reviewSummaryLinkNote}>{item.note}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.reviewSummaryText}>No overlapping articles surfaced.</p>
            )}
          </article>
        </div>
      </div>
    </section>
  );
}
