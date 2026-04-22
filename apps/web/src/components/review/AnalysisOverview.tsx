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

const FACT_CHECK_PLACEHOLDER = "Run Fact Check to populate this section.";
const HUMAN_VOICE_PLACEHOLDER = "Run Human Voice to estimate AI-writing patterns.";

function humanVoiceHeadline(score: number | null): string {
  if (score === null) {
    return HUMAN_VOICE_PLACEHOLDER;
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

function overlapHeadline(
  overlapCount: number,
  noveltyScore: number | null | undefined,
  factCheckRan: boolean,
): string {
  if (!factCheckRan) {
    return "Run Fact Check to surface overlapping articles.";
  }
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

function hasAgentRun(
  agentResults: ArtifactAgentResult[],
  agentId: string,
  documentRevisionId?: string | null,
): boolean {
  return findAgentResult(agentResults, agentId, documentRevisionId) !== null;
}

function normalizeSummary(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function humanVoiceDrag(aiLikelihood: number | null | undefined): string {
  if (aiLikelihood === null || aiLikelihood === undefined) {
    return "no estimate";
  }
  if (aiLikelihood >= 0.7) {
    return "strong drag";
  }
  if (aiLikelihood >= 0.4) {
    return "moderate drag";
  }
  if (aiLikelihood > 0) {
    return "minor drag";
  }
  return "no drag";
}

function buildScoreBreakdown(
  summary: ArtifactSummary,
  overlapCount: number,
  factCheckRan: boolean,
  aiLikelihoodRan: boolean,
): string[] {
  const lines = ["Baseline 72."];
  if (aiLikelihoodRan) {
    const aiPct = formatPercent(summary.ai_likelihood);
    lines.push(`Human Voice: ${aiPct} AI likelihood (${humanVoiceDrag(summary.ai_likelihood)}).`);
  } else {
    lines.push("Human Voice: not run — no AI-pattern drag applied.");
  }
  if (factCheckRan) {
    const novelty = summary.novelty_score;
    if (overlapCount > 0 && novelty !== null && novelty !== undefined) {
      const articleLabel = overlapCount === 1 ? "article" : "articles";
      lines.push(
        `Fact Check: ${overlapCount} overlapping ${articleLabel} (${formatPercent(novelty)} originality).`,
      );
    } else {
      lines.push("Fact Check: no overlapping articles — no overlap penalty.");
    }
  } else {
    lines.push("Fact Check: not run — no research bonus or overlap penalty applied.");
  }
  if (!factCheckRan && !aiLikelihoodRan) {
    lines.push("Run Fact Check and Human Voice for a meaningful score.");
  }
  return lines;
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
  const factCheckRan = hasAgentRun(agentResults, "fact_check", documentRevisionId);
  const aiLikelihoodRan = hasAgentRun(agentResults, "ai_likelihood", documentRevisionId);
  const aiResult = findAgentResult(agentResults, "ai_likelihood", documentRevisionId);

  const voiceScore = aiLikelihoodRan ? humanVoiceScore(summary.ai_likelihood) : null;
  const voiceFindingsCount = aiResult?.findings.length ?? 0;
  const overlapItems = factCheckRan ? overview?.overlap_items ?? [] : [];
  const structuralCompleteness = overview?.structural_completeness;

  const tlDr = factCheckRan
    ? overview?.tl_dr || summary.tl_dr || overview?.content_summary || null
    : null;

  const researchSummaryRaw = factCheckRan ? overview?.research_summary?.trim() ?? "" : "";
  const researchSummaryNormalized = normalizeSummary(researchSummaryRaw);
  const researchSummary =
    researchSummaryRaw &&
    researchSummaryNormalized !== normalizeSummary(tlDr ?? "") &&
    researchSummaryNormalized !== normalizeSummary(summary.verdict)
      ? researchSummaryRaw
      : null;

  const audienceSummary = factCheckRan
    ? overview?.inferred_audience || summary.audience_summary || null
    : null;

  const articleProfilePills = factCheckRan
    ? [titleCase(overview?.article_format), titleCase(overview?.reading_difficulty)].filter(
        (item): item is string => Boolean(item),
      )
    : [];

  const textMetricPills = [
    formatCount(overview?.word_count ?? summary.word_count),
    formatReadingTime(overview?.estimated_reading_time_minutes ?? summary.estimated_reading_time_minutes),
  ];

  const completenessItems: Array<{ label: string; complete: boolean; tooltip: string }> = factCheckRan
    ? [
        {
          label: "Intro",
          complete: structuralCompleteness?.has_intro ?? false,
          tooltip: "Detected by checking whether the opening source block contains non-empty text.",
        },
        {
          label: "Headings",
          complete: structuralCompleteness?.has_headings ?? false,
          tooltip: "Detected by checking whether the draft contains at least one heading in the source blocks.",
        },
        {
          label: "Conclusion",
          complete: structuralCompleteness?.has_conclusion ?? false,
          tooltip:
            'Detected by scanning the closing block for phrases like "in summary", "overall", "bottom line", "in conclusion", or "to sum up". A section titled "Conclusion" alone will not match this heuristic.',
        },
      ]
    : [];

  const showOverallScore = factCheckRan || aiLikelihoodRan;
  const scoreBreakdownLines = buildScoreBreakdown(summary, overlapItems.length, factCheckRan, aiLikelihoodRan);

  return (
    <section className={styles.analysisOverview} data-testid="analysis-overview">
      <div className={styles.analysisOverviewStack}>
        <div>
          <div className={styles.sectionTitle}>Analysis overview</div>
          <div className={styles.analysisOverviewHero}>
            <div className={styles.analysisOverviewScorePanel}>
              <div className={styles.metricLabel}>Overall score</div>
              <div className={styles.analysisOverviewScoreValue}>
                {showOverallScore && summary.overall_score != null ? `${summary.overall_score}%` : "\u2014"}
              </div>
            </div>
            <div className={styles.analysisOverviewVerdict} data-testid="overall-score-breakdown">
              {scoreBreakdownLines.map((line) => (
                <p key={line} className={styles.analysisOverviewSupportLine}>
                  {line}
                </p>
              ))}
            </div>
          </div>
        </div>

        <div className={styles.analysisOverviewTextBlock}>
          <div className={styles.metricLabel}>TL;DR</div>
          {tlDr ? (
            <p className={styles.analysisOverviewBody}>{tlDr}</p>
          ) : (
            <p className={styles.analysisOverviewSupportLine}>{FACT_CHECK_PLACEHOLDER}</p>
          )}
        </div>

        <div className={styles.analysisOverviewGrid}>
          <article className={styles.analysisOverviewCard}>
            <div className={styles.analysisOverviewCardHeader}>
              <div className={styles.metricLabel}>Article profile</div>
            </div>
            <div className={styles.analysisOverviewPills}>
              {textMetricPills.map((item) => (
                <span key={item} className={styles.pill}>
                  {item}
                </span>
              ))}
            </div>
            {factCheckRan ? (
              <>
                {articleProfilePills.length > 0 ? (
                  <div className={styles.analysisOverviewPills}>
                    {articleProfilePills.map((item) => (
                      <span key={item} className={styles.pill}>
                        {item}
                      </span>
                    ))}
                  </div>
                ) : null}
                <div className={styles.analysisOverviewPills}>
                  {completenessItems.map((item) => (
                    <span
                      key={item.label}
                      className={styles.pill}
                      title={item.tooltip}
                      aria-label={`${item.label}: ${item.complete ? "present" : "needs work"}. ${item.tooltip}`}
                    >
                      {item.label}: {item.complete ? "present" : "needs work"}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <p className={styles.analysisOverviewSupportLine}>
                Run Fact Check to profile the article (format, density, and structural coverage).
              </p>
            )}
          </article>

          <article className={styles.analysisOverviewCard} data-testid="overlap-research-card">
            <div className={styles.analysisOverviewCardHeader}>
              <div className={styles.metricLabel}>Overlap research</div>
              <span className={styles.analysisOverviewMeta}>
                Originality signal {factCheckRan ? formatPercent(summary.novelty_score) : "\u2014"}
              </span>
            </div>
            <p
              className={
                factCheckRan ? styles.analysisOverviewBody : styles.analysisOverviewSupportLine
              }
            >
              {overlapHeadline(overlapItems.length, summary.novelty_score, factCheckRan)}
            </p>
            {factCheckRan ? (
              <p className={styles.analysisOverviewSupportLine}>
                From Fact Check&rsquo;s web-research pass. Lower originality means the draft restates ideas already widely covered.
              </p>
            ) : null}
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
            <p className={styles.analysisOverviewSupportLine}>
              {aiLikelihoodRan
                ? voiceFindingsCount > 0
                  ? `From Human Voice. ${voiceFindingsCount} AI-pattern signal${
                      voiceFindingsCount === 1 ? "" : "s"
                    } flagged as inline comments below.`
                  : "From Human Voice. No AI-pattern signals were flagged."
                : HUMAN_VOICE_PLACEHOLDER}
            </p>
          </article>

          <article className={styles.analysisOverviewCard}>
            <div className={styles.analysisOverviewCardHeader}>
              <div className={styles.metricLabel}>Audience</div>
            </div>
            {audienceSummary ? (
              <p className={styles.analysisOverviewBody}>{audienceSummary}</p>
            ) : (
              <p className={styles.analysisOverviewSupportLine}>{FACT_CHECK_PLACEHOLDER}</p>
            )}
          </article>
        </div>

        {researchSummary ? (
          <div className={styles.analysisOverviewTextBlock}>
            <div className={styles.metricLabel}>Research summary</div>
            <p className={styles.analysisOverviewBody}>{researchSummary}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
