import { useEffect, useMemo, useState } from "react";

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
  localError: string | null;
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
  localError,
  onDecisionChange,
  onRejectAll,
  onApply,
}: RevisedMarkdownPanelProps) {
  const [viewMode, setViewMode] = useState<DiffViewMode>(mode === "rewrite" ? "side-by-side" : "inline");
  useEffect(() => {
    setViewMode(mode === "rewrite" ? "side-by-side" : "inline");
  }, [mode]);
  const acceptedItems = diffItems.filter((item) => item.decision === "accepted").length;
  const pendingItems = diffItems.filter((item) => item.decision === "pending").length;
  const canApplyInline = !applied && acceptedItems > 0 && !savingDecision && !applyingRevision;
  const canApplySideBySide = !applied && !savingDecision && !applyingRevision;
  const activeViewMode = mode === "surgical" ? "inline" : viewMode;
  const showViewToggle = mode === "rewrite";
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
                : activeViewMode === "inline" && acceptedItems > 0
                  ? pendingItems > 0
                    ? `Apply will include ${acceptedItems} accepted change${acceptedItems === 1 ? "" : "s"} and leave ${pendingItems} pending or unreviewed diff ${pendingItems === 1 ? "item" : "items"} unchanged.`
                    : `Apply will include only the ${acceptedItems} accepted change${acceptedItems === 1 ? "" : "s"} and leave any rejected changes out of the revised draft.`
                  : activeViewMode === "inline" && pendingItems > 0
                    ? "Accept at least one diff item to enable apply. Pending or unreviewed changes will remain unchanged until they are reviewed."
                  : activeViewMode === "side-by-side"
                    ? "Review the full revision side by side, then apply or discard it as one decision."
                    : "Accept at least one diff item to apply the reviewed markdown. Pending or unreviewed changes will remain unchanged."}
            </p>
          </div>
          <div className={styles.diffReviewHeaderActions}>
            {showViewToggle ? (
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
            ) : null}
          </div>
        </div>

        {activeViewMode === "side-by-side" ? (
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
                {localError ? (
                  <p className={styles.errorBanner} data-testid="revised-markdown-local-error" role="alert">
                    {localError}
                  </p>
                ) : null}
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
                      {mode === "surgical"
                        ? buildWordDiffSegments(block.removedText, block.addedText).map((segment, segmentIndex) => {
                            if (segment.kind === "equal") {
                              return <span key={`${block.diffId}-equal-${segmentIndex}`}>{segment.text}</span>;
                            }
                            if (segment.kind === "removed") {
                              return (
                                <span
                                  key={`${block.diffId}-removed-${segmentIndex}`}
                                  className={styles.inlineDiffRemoved}
                                >
                                  {segment.text}
                                </span>
                              );
                            }
                            return (
                              <span
                                key={`${block.diffId}-added-${segmentIndex}`}
                                className={styles.inlineDiffAdded}
                              >
                                {segment.text}
                              </span>
                            );
                          })
                        : (
                            <>
                              {block.removedText ? (
                                <span className={styles.inlineDiffRemoved}>{block.removedText}</span>
                              ) : null}
                              {block.addedText ? (
                                <span className={styles.inlineDiffAdded}>{block.addedText}</span>
                              ) : null}
                            </>
                          )}
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
                  {applyingRevision ? "Applying revision..." : "Apply accepted changes"}
                </button>
                {localError ? (
                  <p className={styles.errorBanner} data-testid="revised-markdown-local-error" role="alert">
                    {localError}
                  </p>
                ) : null}
              </div>
            ) : null}
            {mode === "rewrite" ? (
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
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}

type InlineDiffBlock =
  | { kind: "unchanged"; text: string }
  | { kind: "changed"; diffId: string; removedText: string; addedText: string };

type WordDiffSegment = { kind: "equal" | "added" | "removed"; text: string };

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

function buildWordDiffSegments(beforeText: string, afterText: string): WordDiffSegment[] {
  if (!beforeText && !afterText) {
    return [];
  }

  const beforeTokens = tokenizeDiffText(beforeText);
  const afterTokens = tokenizeDiffText(afterText);

  if (beforeTokens.length === 0) {
    return [{ kind: "added", text: afterText }];
  }
  if (afterTokens.length === 0) {
    return [{ kind: "removed", text: beforeText }];
  }
  if (beforeTokens.length * afterTokens.length > 16000) {
    return [
      ...(beforeText ? [{ kind: "removed", text: beforeText } satisfies WordDiffSegment] : []),
      ...(afterText ? [{ kind: "added", text: afterText } satisfies WordDiffSegment] : []),
    ];
  }

  const matrix = Array.from({ length: beforeTokens.length + 1 }, () =>
    Array.from({ length: afterTokens.length + 1 }, () => 0),
  );

  for (let beforeIndex = beforeTokens.length - 1; beforeIndex >= 0; beforeIndex -= 1) {
    for (let afterIndex = afterTokens.length - 1; afterIndex >= 0; afterIndex -= 1) {
      if (beforeTokens[beforeIndex] === afterTokens[afterIndex]) {
        matrix[beforeIndex][afterIndex] = matrix[beforeIndex + 1][afterIndex + 1] + 1;
      } else {
        matrix[beforeIndex][afterIndex] = Math.max(
          matrix[beforeIndex + 1][afterIndex],
          matrix[beforeIndex][afterIndex + 1],
        );
      }
    }
  }

  const segments: WordDiffSegment[] = [];
  let beforeIndex = 0;
  let afterIndex = 0;

  while (beforeIndex < beforeTokens.length && afterIndex < afterTokens.length) {
    if (beforeTokens[beforeIndex] === afterTokens[afterIndex]) {
      segments.push({ kind: "equal", text: beforeTokens[beforeIndex] });
      beforeIndex += 1;
      afterIndex += 1;
      continue;
    }

    if (matrix[beforeIndex + 1][afterIndex] >= matrix[beforeIndex][afterIndex + 1]) {
      segments.push({ kind: "removed", text: beforeTokens[beforeIndex] });
      beforeIndex += 1;
      continue;
    }

    segments.push({ kind: "added", text: afterTokens[afterIndex] });
    afterIndex += 1;
  }

  while (beforeIndex < beforeTokens.length) {
    segments.push({ kind: "removed", text: beforeTokens[beforeIndex] });
    beforeIndex += 1;
  }

  while (afterIndex < afterTokens.length) {
    segments.push({ kind: "added", text: afterTokens[afterIndex] });
    afterIndex += 1;
  }

  return mergeWordDiffSegments(segments);
}

function tokenizeDiffText(text: string): string[] {
  return text.match(/\s+|[^\s]+/g) ?? [];
}

function mergeWordDiffSegments(segments: WordDiffSegment[]): WordDiffSegment[] {
  const merged: WordDiffSegment[] = [];

  segments.forEach((segment) => {
    const previousSegment = merged.at(-1);
    if (previousSegment && previousSegment.kind === segment.kind) {
      previousSegment.text += segment.text;
      return;
    }
    merged.push({ ...segment });
  });

  return merged;
}
