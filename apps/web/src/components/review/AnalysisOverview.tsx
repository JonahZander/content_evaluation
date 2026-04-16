import styles from "@/components/ReviewWorkbench.module.css";
import type { ArtifactAgentResult, ArtifactReviewSummary, ArtifactSummary } from "@/lib/types";

interface AnalysisOverviewProps {
  summary: ArtifactSummary | null;
  reviewSummary: ArtifactReviewSummary | null;
  agentResults: ArtifactAgentResult[];
  documentRevisionId?: string | null;
}

function formatPercent(score: number | null | undefined): string {
  if (score === null || score === undefined) {
    return "—";
  }
  return `${Math.round(score * 100)}%`;
}

function formatCount(count: number | null | undefined): string {
  if (count === null || count === undefined || Number.isNaN(count) || count <= 0) {
    return "Pending";
  }

  return `${new Intl.NumberFormat("en-US").format(count)} words`;
}

function formatReadingTime(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes) || minutes <= 0) {
    return "Reading time pending";
  }

  return `${minutes} min read`;
}

function titleCase(label: string | null | undefined): string | null {
  if (!label) {
    return null;
  }

  return label
    .split(/[\s_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function humanVoiceScore(aiLikelihood: number | null | undefined): number | null {
  if (aiLikelihood === null || aiLikelihood === undefined) {
    return null;
  }

  return Math.max(0, Math.min(1, 1 - aiLikelihood));
}

function humanVoiceHeadline(score: number | null): string {
  if (score === null) {
    return "Human voice analysis pending.";
  }
  if (score >= 0.85) {
    return "Strong human voice with only light AI-pattern signals.";
  }
  if (score >= 0.65) {
    return "Mostly human voice, with some AI-like phrasing worth tightening.";
  }
  if (score >= 0.4) {
    return "Mixed voice signals. The draft reads partly natural and partly templated.";
  }
  return "Heavy AI-pattern signals surfaced in the current draft.";
}

function overlapHeadline(overlapCount: number, noveltyScore: number | null | undefined): string {
  if (overlapCount === 0) {
    return "No significant overlap detected in the research pass.";
  }

  const articleLabel = overlapCount === 1 ? "article" : "articles";
  if (noveltyScore === null || noveltyScore === undefined) {
    return `${overlapCount} overlapping ${articleLabel} found.`;
  }
  if (noveltyScore >= 0.75) {
    return `Mostly original, with light overlap across ${overlapCount} related ${articleLabel}.`;
  }
  if (noveltyScore >= 0.45) {
    return `Moderate overlap with ${overlapCount} related ${articleLabel}.`;
  }
  return `High overlap with ${overlapCount} related ${articleLabel}.`;
}

function findAgentResult(
  agentResults: ArtifactAgentResult[],
  agentId: string,
  documentRevisionId?: string | null,
): ArtifactAgentResult | null {
  let fallback: ArtifactAgentResult | null = null;
  for (let index = agentResults.length - 1; index >= 0; index -= 1) {
    const result = agentResults[index];
    if (result.agent_id !== agentId) {
      continue;
    }
    if (
      documentRevisionId !== null &&
      documentRevisionId !== undefined &&
      result.document_revision_id !== null &&
      result.document_revision_id !== undefined &&
      result.document_revision_id !== documentRevisionId
    ) {
      fallback ??= result;
      continue;
    }
    return result;
  }
  return fallback;
}

export function AnalysisOverview({
  summary,
  reviewSummary,
  agentResults,
  documentRevisionId,
}: AnalysisOverviewProps) {
  if (summary === null) {
    return null;
  }

  const overview = reviewSummary;
  const aiResult = findAgentResult(agentResults, "ai_likelihood", documentRevisionId);
  const voiceScore = humanVoiceScore(summary.ai_likelihood);
  const overlapItems = overview?.overlap_items ?? [];
  const structuralCompleteness = overview?.structural_completeness;
  const voiceFindings = aiResult
    ? [...aiResult.findings]
        .sort((left, right) => right.confidence - left.confidence)
        .map((finding) => finding.rationale.trim())
        .filter(Boolean)
        .slice(0, 2)
    : [];

  if (voiceFindings.length === 0 && aiResult?.summary?.trim()) {
    voiceFindings.push(aiResult.summary.trim());
  }
  if (voiceFindings.length === 0) {
    voiceFindings.push("No AI writing patterns detected.");
  }

  const tlDr = overview?.tl_dr || summary.tl_dr || overview?.content_summary || "Pending";
  const researchSummary = overview?.research_summary || "Pending";
  const audienceSummary = overview?.inferred_audience || summary.audience_summary || "Pending";
  const articleProfileItems = [
    titleCase(overview?.article_format),
    titleCase(overview?.reading_difficulty),
    formatCount(overview?.word_count ?? summary.word_count),
    formatReadingTime(overview?.estimated_reading_time_minutes ?? summary.estimated_reading_time_minutes),
  ].filter((item): item is string => Boolean(item));

  const completenessItems = [
    { label: "Intro", complete: structuralCompleteness?.has_intro ?? false },
    { label: "Headings", complete: structuralCompleteness?.has_headings ?? false },
    { label: "Conclusion", complete: structuralCompleteness?.has_conclusion ?? false },
  ];

  return (
    <section className={styles.analysisOverview} data-testid="analysis-overview">
      <div className={styles.analysisOverviewStack}>
        <div>
          <div className={styles.sectionTitle}>Analysis overview</div>
          <div className={styles.analysisOverviewHero}>
            <div className={styles.analysisOverviewScorePanel}>
              <div className={styles.metricLabel}>Overall score</div>
              <div className={styles.analysisOverviewScoreValue}>{summary.overall_score != null ? `${summary.overall_score}%` : "\u2014"}</div>
            </div>
            <p className={styles.analysisOverviewVerdict}>{summary.verdict || "Analysis completed."}</p>
          </div>
        </div>

        <div className={styles.analysisOverviewTextBlock}>
          <div className={styles.metricLabel}>TL;DR</div>
          <p className={styles.analysisOverviewBody}>{tlDr}</p>
        </div>

        <div className={styles.analysisOverviewGrid}>
          <article className={styles.analysisOverviewCard}>
            <div className={styles.analysisOverviewCardHeader}>
              <div className={styles.metricLabel}>Article profile</div>
            </div>
            <div className={styles.analysisOverviewPills}>
              {articleProfileItems.map((item) => (
                <span key={item} className={styles.pill}>
                  {item}
                </span>
              ))}
            </div>
            <div className={styles.analysisOverviewPills}>
              {completenessItems.map((item) => (
                <span key={item.label} className={styles.pill}>
                  {item.label}: {item.complete ? "present" : "needs work"}
                </span>
              ))}
            </div>
          </article>

          <article className={styles.analysisOverviewCard} data-testid="overlap-research-card">
            <div className={styles.analysisOverviewCardHeader}>
              <div className={styles.metricLabel}>Overlap research</div>
              <span className={styles.analysisOverviewMeta}>
                Originality signal {formatPercent(summary.novelty_score)}
              </span>
            </div>
            <p className={styles.analysisOverviewBody}>{overlapHeadline(overlapItems.length, summary.novelty_score)}</p>
            {overlapItems.length > 0 ? (
              <ul className={styles.analysisOverviewLinks}>
                {overlapItems.map((item) => (
                  <li key={`${item.url}-${item.title}`}>
                    <a className={styles.sourceLink} href={item.url} target="_blank" rel="noreferrer">
                      {item.title}
                    </a>
                    <div className={styles.analysisOverviewLinkNote}>{item.note}</div>
                  </li>
                ))}
              </ul>
            ) : null}
          </article>

          <article className={styles.analysisOverviewCard} data-testid="human-voice-card">
            <div className={styles.analysisOverviewCardHeader}>
              <div className={styles.metricLabel}>Human voice</div>
              <span className={styles.analysisOverviewMeta}>Voice signal {formatPercent(voiceScore)}</span>
            </div>
            <p className={styles.analysisOverviewBody}>{humanVoiceHeadline(voiceScore)}</p>
            <div className={styles.analysisOverviewSupportingCopy}>
              {voiceFindings.map((finding, index) => (
                <p key={`${index}-${finding.slice(0, 40)}`} className={styles.analysisOverviewSupportLine}>
                  {finding}
                </p>
              ))}
            </div>
          </article>

          <article className={styles.analysisOverviewCard}>
            <div className={styles.analysisOverviewCardHeader}>
              <div className={styles.metricLabel}>Audience</div>
            </div>
            <p className={styles.analysisOverviewBody}>{audienceSummary}</p>
          </article>
        </div>

        <div className={styles.analysisOverviewTextBlock}>
          <div className={styles.metricLabel}>Research summary</div>
          <p className={styles.analysisOverviewBody}>{researchSummary}</p>
        </div>
      </div>
    </section>
  );
}
