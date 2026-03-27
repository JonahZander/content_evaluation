import { useMemo, useState } from "react";

import styles from "@/components/ReviewWorkbench.module.css";

type DiffDecision = "pending" | "accepted" | "rejected";
type DiffViewMode = "side-by-side" | "inline";

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
  onRejectAll: () => void;
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
  onRejectAll,
  onApply,
}: RevisedMarkdownPanelProps) {
  const [viewMode, setViewMode] = useState<DiffViewMode>(mode === "rewrite" ? "side-by-side" : "inline");
  const pendingItems = diffItems.filter((item) => item.decision === "pending").length;
  const canApplyInline = !applied && pendingItems === 0 && diffItems.length > 0 && !savingDecision && !applyingRevision;
  const canApplySideBySide = !applied && !savingDecision && !applyingRevision;
  const inlineBlocks = useMemo(
    () => buildInlineBlocks(originalMarkdown, diffItems),
    [diffItems, originalMarkdown],
  );

  return (
    <section className={styles.reviewSummaryPanel} data-testid="revised-markdown-panel">
      <div className={styles.diffReviewPanel}>
        <div className={styles.diffReviewHeader}>
          <div className={styles.diffReviewHeaderText}>
            <h2 className={styles.sectionTitle}>Revised markdown</h2>
            <div className={styles.revisionModeMeta}>
              <span className={styles.pill}>{mode === "surgical" ? "Apply changes" : "Rewrite draft"}</span>
              {directionPrompt ? <span className={styles.reviewBadge}>Direction: {directionPrompt}</span> : null}
            </div>
            <p className={styles.reviewSummaryText}>
              {applied
                ? "The reviewed revision has been promoted to the working draft. Follow-up analysis is available again."
                : viewMode === "inline" && pendingItems > 0
                  ? `Review ${pendingItems} remaining diff ${pendingItems === 1 ? "item" : "items"} before applying the revision.`
                  : viewMode === "side-by-side"
                    ? "Review the full revision side by side, then apply or discard it as one decision."
                    : "Every diff has a decision. Apply the reviewed markdown when you are ready."}
            </p>
          </div>
          <div className={styles.diffReviewHeaderActions}>
            <div className={styles.diffViewToggle} data-testid="diff-view-toggle">
              <button
                className={`${styles.diffViewToggleButton} ${viewMode === "side-by-side" ? styles.diffViewToggleActive : ""}`}
                data-testid="diff-view-toggle-side-by-side"
                type="button"
                onClick={() => setViewMode("side-by-side")}
              >
                Side by side
              </button>
              <button
                className={`${styles.diffViewToggleButton} ${viewMode === "inline" ? styles.diffViewToggleActive : ""}`}
                data-testid="diff-view-toggle-inline"
                type="button"
                onClick={() => setViewMode("inline")}
              >
                Inline
              </button>
            </div>
          </div>
        </div>

        {viewMode === "side-by-side" ? (
          <>
            <div className={styles.reviewSummaryGrid}>
              <article className={styles.reviewSummaryCard}>
                <div className={styles.metricLabel}>Original cleaner output</div>
                <pre className={styles.diffMarkdownPreview} data-testid="revised-markdown-original">
                  {originalMarkdown || "No original markdown available."}
                </pre>
              </article>
              <article className={styles.reviewSummaryCard}>
                <div className={styles.metricLabel}>Candidate revision</div>
                <pre className={styles.diffMarkdownPreview} data-testid="revised-markdown-candidate">
                  {candidateMarkdown || "No revised markdown available."}
                </pre>
              </article>
            </div>
            {!applied ? (
              <div className={styles.diffApplyRow}>
                <button
                  className={styles.button}
                  data-testid="apply-revised-markdown-button"
                  type="button"
                  onClick={onApply}
                  disabled={!canApplySideBySide}
                >
                  {applyingRevision ? "Applying revision..." : "Apply full revision"}
                </button>
                <button
                  className={styles.ghostButton}
                  data-testid="discard-revised-markdown-button"
                  type="button"
                  onClick={onRejectAll}
                  disabled={savingDecision || applyingRevision}
                >
                  Discard revision
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <>
            <article className={styles.reviewSummaryCard}>
              <div className={styles.metricLabel}>Inline review</div>
              <pre className={styles.inlineDiffView} data-testid="inline-diff-view">
                {inlineBlocks.map((block, index) => {
                  if (block.kind === "unchanged") {
                    return <span key={`unchanged-${index}`}>{block.text}</span>;
                  }

                  const item = diffItems.find((candidate) => candidate.id === block.diffId);
                  const decision = item?.decision ?? "pending";

                  return (
                    <span key={block.diffId} data-testid={`diff-item-${block.diffId}`}>
                      {block.removedText ? (
                        <span className={styles.inlineDiffRemoved}>{block.removedText}</span>
                      ) : null}
                      {block.addedText ? (
                        <span className={styles.inlineDiffAdded}>{block.addedText}</span>
                      ) : null}
                      {!applied ? (
                        <span className={styles.inlineDiffActions} data-diff-id={block.diffId}>
                          <span className={styles.reviewBadge} data-testid={`diff-item-status-${block.diffId}`}>
                            {decision}
                          </span>
                          <button
                            className={`${styles.inlineDiffButton} ${decision === "accepted" ? styles.inlineDiffButtonActive : ""}`}
                            data-testid={`diff-decision-${block.diffId}-accepted`}
                            type="button"
                            onClick={() => onDecisionChange(block.diffId, "accepted")}
                            title="Keep change"
                            aria-label="Keep change"
                            disabled={savingDecision || applyingRevision}
                          >
                            ✓
                          </button>
                          <button
                            className={`${styles.inlineDiffButton} ${decision === "rejected" ? styles.inlineDiffButtonActive : ""}`}
                            data-testid={`diff-decision-${block.diffId}-rejected`}
                            type="button"
                            onClick={() => onDecisionChange(block.diffId, "rejected")}
                            title="Discard change"
                            aria-label="Discard change"
                            disabled={savingDecision || applyingRevision}
                          >
                            ✕
                          </button>
                        </span>
                      ) : null}
                    </span>
                  );
                })}
              </pre>
            </article>
            {!applied ? (
              <div className={styles.diffApplyRow}>
                <button
                  className={styles.button}
                  data-testid="apply-revised-markdown-button"
                  type="button"
                  onClick={onApply}
                  disabled={!canApplyInline}
                >
                  {applyingRevision ? "Applying revision..." : "Apply reviewed markdown"}
                </button>
              </div>
            ) : null}
            <div className={styles.diffItemList}>
              {diffItems.map((item, index) => (
                <article key={item.id} className={styles.reviewSummaryCard} data-testid={`diff-summary-${item.id}`}>
                  <div className={styles.diffItemHeader}>
                    <div>
                      <div className={styles.metricLabel}>Diff {index + 1}</div>
                      <div className={styles.diffItemTitle}>
                        {item.changeType} lines {formatLineRange(item.originalStartLine, item.originalEndLine)}
                        {" -> "}
                        {formatLineRange(item.candidateStartLine, item.candidateEndLine)}
                      </div>
                    </div>
                    <span className={styles.pill}>{item.decision}</span>
                  </div>
                  <div className={styles.diffItemGrid}>
                    <div>
                      <div className={styles.metricLabel}>Before</div>
                      <pre className={styles.diffSnippetPreview}>{item.beforeText || "(no content)"}</pre>
                    </div>
                    <div>
                      <div className={styles.metricLabel}>After</div>
                      <pre className={styles.diffSnippetPreview}>{item.afterText || "(no content)"}</pre>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

type InlineDiffBlock =
  | { kind: "unchanged"; text: string }
  | { kind: "changed"; diffId: string; removedText: string; addedText: string };

function buildInlineBlocks(
  originalMarkdown: string,
  diffItems: RevisedMarkdownDiffItemView[],
): InlineDiffBlock[] {
  const sortedItems = [...diffItems].sort((left, right) => {
    if (left.originalStartLine !== right.originalStartLine) {
      return left.originalStartLine - right.originalStartLine;
    }
    if (left.candidateStartLine !== right.candidateStartLine) {
      return left.candidateStartLine - right.candidateStartLine;
    }
    return left.id.localeCompare(right.id);
  });

  const blocks: InlineDiffBlock[] = [];
  let cursor = 0;

  sortedItems.forEach((item) => {
    const { start, end } = locateDiffBounds(originalMarkdown, item, cursor);
    if (start > cursor) {
      blocks.push({ kind: "unchanged", text: originalMarkdown.slice(cursor, start) });
    }

    blocks.push({
      kind: "changed",
      diffId: item.id,
      removedText: start < end ? originalMarkdown.slice(start, end) : item.beforeText,
      addedText: item.afterText,
    });

    cursor = Math.max(cursor, end);
  });

  if (cursor < originalMarkdown.length) {
    blocks.push({ kind: "unchanged", text: originalMarkdown.slice(cursor) });
  }

  return blocks;
}

function locateDiffBounds(
  originalMarkdown: string,
  item: RevisedMarkdownDiffItemView,
  cursor: number,
): { start: number; end: number } {
  if (item.beforeText) {
    const matchedIndex = originalMarkdown.indexOf(item.beforeText, cursor);
    if (matchedIndex !== -1) {
      return { start: matchedIndex, end: matchedIndex + item.beforeText.length };
    }
  }

  const lineStarts = computeLineStarts(originalMarkdown);
  const start = lineStartAt(lineStarts, item.originalStartLine, cursor);
  const end = lineStartAt(lineStarts, item.originalEndLine + 1, originalMarkdown.length);
  return { start, end: Math.max(start, end) };
}

function computeLineStarts(text: string): number[] {
  const lineStarts = [0];
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "\n") {
      lineStarts.push(index + 1);
    }
  }
  return lineStarts;
}

function lineStartAt(lineStarts: number[], lineNumber: number, fallback: number): number {
  if (lineNumber <= 0) {
    return fallback;
  }
  return lineStarts[lineNumber - 1] ?? fallback;
}

function formatLineRange(start: number, end: number): string {
  if (start <= 0 && end <= 0) {
    return "n/a";
  }
  if (start === end || end <= 0) {
    return String(start);
  }
  return `${start}-${end}`;
}
