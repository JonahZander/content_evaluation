import styles from "@/components/ReviewWorkbench.module.css";
import type { ArtifactReviewSummary } from "@/lib/types";

interface ReviewSummaryPanelProps {
  reviewSummary: ArtifactReviewSummary | null;
}

type ReviewSummaryView = ArtifactReviewSummary & {
  tl_dr?: string;
  word_count?: number;
  estimated_reading_time_minutes?: number;
  article_format?: string;
  reading_difficulty?: string;
  structural_completeness?: {
    has_intro?: boolean;
    has_headings?: boolean;
    has_conclusion?: boolean;
  };
  main_claims?: Array<{
    claim_text: string;
    verdict: string;
    evidence_summary: string;
    source_links?: string[];
    anchor_quote?: string;
    value_add?: string;
    official_source_links?: string[];
    related_post_links?: string[];
  }>;
};

export function ReviewSummaryPanel({ reviewSummary }: ReviewSummaryPanelProps) {
  if (reviewSummary === null) {
    return null;
  }

  const summary = reviewSummary as ReviewSummaryView;
  const hasOverlapItems = summary.overlap_items.length > 0;
  const mainClaims = summary.main_claims ?? [];
  const hasMainClaims = mainClaims.length > 0;
  const structuralCompleteness = summary.structural_completeness;
  const completenessItems = [
    { label: "Intro", value: structuralCompleteness?.has_intro ?? false },
    { label: "Headings", value: structuralCompleteness?.has_headings ?? false },
    { label: "Conclusion", value: structuralCompleteness?.has_conclusion ?? false },
  ];

  return (
    <section className={styles.reviewSummaryPanel} data-testid="review-summary-panel">
      <div>
        <h2 className={styles.sectionTitle}>Review summary</h2>
        <div className={styles.reviewSummaryGrid}>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>TL;DR</div>
            <p className={styles.reviewSummaryText}>
              {summary.tl_dr || summary.content_summary || "Pending"}
            </p>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Article profile</div>
            <div className={styles.reviewSummaryText}>
              <span className={styles.pill}>{summary.article_format || "Format pending"}</span>{" "}
              <span className={styles.pill}>{summary.reading_difficulty || "Difficulty pending"}</span>{" "}
              <span className={styles.pill}>
                {summary.word_count ? `${summary.word_count} words` : "Word count pending"}
              </span>{" "}
              <span className={styles.pill}>
                {summary.estimated_reading_time_minutes
                  ? `${summary.estimated_reading_time_minutes} min read`
                  : "Reading time pending"}
              </span>
            </div>
            <div className={styles.reviewSummaryText}>
              {completenessItems.map((item) => (
                <span key={item.label} className={styles.pill}>
                  {item.label}: {item.value ? "yes" : "no"}
                </span>
              ))}
            </div>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Research summary</div>
            <p className={styles.reviewSummaryText}>
              {summary.research_summary || "Pending"}
            </p>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Main claims</div>
            {hasMainClaims ? (
              <div className={styles.claimEvidencePanel}>
                {mainClaims.map((claim) => {
                  const links = [
                    ...((claim.official_source_links ?? []).map((link) => ({ label: "Official", href: link }))),
                    ...((claim.related_post_links ?? []).map((link) => ({ label: "Related", href: link }))),
                    ...((claim.source_links ?? []).map((link) => ({ label: "Source", href: link }))),
                  ];
                  return (
                    <article key={`${claim.claim_text}-${claim.verdict}`} className={styles.claimEvidenceCard}>
                      <div className={styles.claimEvidenceHeader}>
                        <span className={styles.claimEvidenceVerdict}>Verdict: {claim.verdict}</span>
                        <span className={styles.claimEvidenceClaim}>{claim.claim_text}</span>
                      </div>
                      <p className={styles.claimEvidenceText}>{claim.evidence_summary}</p>
                      {claim.value_add ? <p className={styles.claimEvidenceText}>{claim.value_add}</p> : null}
                      {claim.anchor_quote ? <p className={styles.claimEvidenceText}>“{claim.anchor_quote}”</p> : null}
                      {links.length > 0 ? (
                        <div className={styles.claimEvidenceLinks}>
                          {links.map((link) => (
                            <a
                              key={`${link.label}-${link.href}`}
                              className={styles.claimEvidenceLink}
                              href={link.href}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {link.label}
                            </a>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className={styles.reviewSummaryText}>No main claims were surfaced yet.</p>
            )}
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Audience</div>
            <p className={styles.reviewSummaryText}>
              {summary.inferred_audience || "Pending"}
            </p>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Overlap research</div>
            {hasOverlapItems ? (
              <ul className={styles.reviewSummaryLinks}>
                {summary.overlap_items.map((item) => (
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
