import type { CSSProperties } from "react";

import styles from "@/components/ReviewWorkbench.module.css";

type DiffDecision = "pending" | "accepted" | "rejected";

export interface RevisedMarkdownDiffItemView {
  id: string;
  changeType: string;
  beforeText: string;
  afterText: string;
  decision: DiffDecision;
  originalStartLine: number;
  originalEndLine: number;
  candidateStartLine: number;
  candidateEndLine: number;
}

interface RevisedMarkdownPanelProps {
  mode: "surgical" | "rewrite";
  directionPrompt: string | null;
  originalMarkdown: string;
  candidateMarkdown: string;
  diffItems: RevisedMarkdownDiffItemView[];
  applied: boolean;
  savingDecision: boolean;
  applyingRevision: boolean;
  onDecisionChange: (diffId: string, decision: Exclude<DiffDecision, "pending">) => void;
  onApply: () => void;
}

export function RevisedMarkdownPanel({
  mode,
  directionPrompt,
  originalMarkdown,
  candidateMarkdown,
  diffItems,
  applied,
  savingDecision,
  applyingRevision,
  onDecisionChange,
  onApply,
}: RevisedMarkdownPanelProps) {
  const pendingItems = diffItems.filter((item) => item.decision === "pending").length;
  const canApply = !applied && pendingItems === 0 && diffItems.length > 0 && !savingDecision && !applyingRevision;

  return (
    <section className={styles.reviewSummaryPanel} data-testid="revised-markdown-panel">
      <div style={{ display: "grid", gap: "16px" }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            gap: "12px",
            alignItems: "center",
          }}
        >
          <div>
            <h2 className={styles.sectionTitle} style={{ marginBottom: "10px" }}>Revised markdown</h2>
            <div className={styles.revisionModeMeta}>
              <span className={styles.pill}>{mode === "surgical" ? "Apply changes" : "Rewrite draft"}</span>
              {directionPrompt ? <span className={styles.reviewBadge}>Direction: {directionPrompt}</span> : null}
            </div>
            <p className={styles.reviewSummaryText} style={{ marginTop: 0 }}>
              {applied
                ? "The reviewed revision has been promoted to the working draft. Follow-up analysis is available again."
                : pendingItems > 0
                  ? `Review ${pendingItems} remaining diff ${pendingItems === 1 ? "item" : "items"} before applying the revision.`
                  : "Every diff has a decision. Apply the reviewed markdown when you are ready."}
            </p>
          </div>
          <button
            className={styles.button}
            data-testid="apply-revised-markdown-button"
            type="button"
            onClick={onApply}
            disabled={!canApply}
          >
            {applyingRevision ? "Applying revision..." : applied ? "Revision applied" : "Apply reviewed markdown"}
          </button>
        </div>

        <div className={styles.reviewSummaryGrid}>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Original cleaner output</div>
            <pre
              data-testid="revised-markdown-original"
              style={{ margin: "10px 0 0", whiteSpace: "pre-wrap", fontFamily: "\"IBM Plex Mono\", monospace", fontSize: "0.9rem", lineHeight: 1.6 }}
            >
              {originalMarkdown || "No original markdown available."}
            </pre>
          </article>
          <article className={styles.reviewSummaryCard}>
            <div className={styles.metricLabel}>Candidate revision</div>
            <pre
              data-testid="revised-markdown-candidate"
              style={{ margin: "10px 0 0", whiteSpace: "pre-wrap", fontFamily: "\"IBM Plex Mono\", monospace", fontSize: "0.9rem", lineHeight: 1.6 }}
            >
              {candidateMarkdown || "No revised markdown available."}
            </pre>
          </article>
        </div>

        <div style={{ display: "grid", gap: "12px" }}>
          {diffItems.map((item, index) => (
            <article key={item.id} className={styles.reviewSummaryCard} data-testid={`diff-item-${item.id}`}>
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  justifyContent: "space-between",
                  gap: "10px",
                  alignItems: "center",
                }}
              >
                <div>
                  <div className={styles.metricLabel}>Diff {index + 1}</div>
                  <div style={{ marginTop: "8px", fontWeight: 600 }}>
                    {item.changeType} lines {formatLineRange(item.originalStartLine, item.originalEndLine)}
                    {" -> "}
                    {formatLineRange(item.candidateStartLine, item.candidateEndLine)}
                  </div>
                </div>
                <span className={styles.pill} data-testid={`diff-item-status-${item.id}`}>
                  {item.decision}
                </span>
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: "12px",
                  marginTop: "14px",
                }}
              >
                <div>
                  <div className={styles.metricLabel}>Before</div>
                  <pre style={panelCodeStyle}>{item.beforeText || "(no content)"}</pre>
                </div>
                <div>
                  <div className={styles.metricLabel}>After</div>
                  <pre style={panelCodeStyle}>{item.afterText || "(no content)"}</pre>
                </div>
              </div>
              {!applied ? (
                <div className={styles.commentActionRow}>
                  <button
                    className={`${styles.stateButton} ${item.decision === "accepted" ? styles.stateButtonActive : ""}`}
                    data-testid={`diff-decision-${item.id}-accepted`}
                    type="button"
                    disabled={savingDecision || applyingRevision}
                    onClick={() => onDecisionChange(item.id, "accepted")}
                  >
                    Accept diff
                  </button>
                  <button
                    className={`${styles.stateButton} ${item.decision === "rejected" ? styles.stateButtonActive : ""}`}
                    data-testid={`diff-decision-${item.id}-rejected`}
                    type="button"
                    disabled={savingDecision || applyingRevision}
                    onClick={() => onDecisionChange(item.id, "rejected")}
                  >
                    Reject diff
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

const panelCodeStyle: CSSProperties = {
  margin: "8px 0 0",
  padding: "12px 14px",
  borderRadius: "16px",
  whiteSpace: "pre-wrap",
  fontFamily: "\"IBM Plex Mono\", monospace",
  fontSize: "0.88rem",
  lineHeight: 1.6,
  background: "rgba(35, 28, 20, 0.06)",
};

function formatLineRange(start: number, end: number): string {
  if (start <= 0 && end <= 0) {
    return "n/a";
  }
  if (start === end || end <= 0) {
    return String(start);
  }
  return `${start}-${end}`;
}
