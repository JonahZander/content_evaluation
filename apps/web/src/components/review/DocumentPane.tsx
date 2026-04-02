import { useMemo, useRef, type MutableRefObject, type ReactNode } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { colorForCategory } from "@/components/review/category-colors";
import {
  anchorPrimarySegment,
  anchorSegments,
  type ArtifactAnchorSegment,
  type ArtifactAnchor,
  type ArtifactBlock,
  type ArtifactComment,
  type ArtifactDocument,
  type ArtifactInlineMark,
  type ArtifactInlineMarkKind,
  type ArtifactThread,
  type ReviewState,
  type SelectionDraft,
} from "@/lib/types";

interface AnchorThread {
  colors: string[];
}

interface SegmentAnchor {
  anchor: ArtifactAnchor;
  colors: string[];
  segment: ArtifactAnchorSegment;
  isPrimarySegment: boolean;
}

interface TextSegment {
  startOffset: number;
  endOffset: number;
  text: string;
  marks: ArtifactInlineMark[];
  anchors: SegmentAnchor[];
  refAnchorIds: string[];
}

interface AnchorRenderGroup {
  kind: "group";
  key: string;
  startOffset: number;
  endOffset: number;
  anchors: SegmentAnchor[];
  refAnchorIds: string[];
  children: ReactNode[];
}

interface PlainRenderGroup {
  kind: "plain";
  key: string;
  content: ReactNode;
}

interface DocumentPaneProps {
  document: ArtifactDocument | null;
  anchors: ArtifactAnchor[];
  threads: ArtifactThread[];
  anchorThreadMap: Map<string, AnchorThread>;
  activeDocumentRevisionId: string | null;
  selectionEnabled?: boolean;
  hoveredAnchorId: string | null;
  hiddenBlockIds?: string[];
  previewPruningEnabled?: boolean;
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>;
  commentRefs: MutableRefObject<Record<string, HTMLElement | null>>;
  onHoverAnchor: (anchorId: string | null) => void;
  onSelectionDraft: (draft: SelectionDraft | null) => void;
  onHideBlock: (blockId: string) => void;
  onRestoreBlock: (blockId: string) => void;
  onRestoreAllBlocks: () => void;
  replyDrafts: Record<string, string>;
  activeReplyComposerId: string | null;
  editingCommentId: string | null;
  editingBody: string;
  onReplyDraftChange: (commentId: string, value: string) => void;
  onToggleReplyComposer: (commentId: string) => void;
  onAddReply: (comment: ArtifactComment) => void;
  onDeleteReply: (replyId: string, commentId: string) => void;
  onReviewState: (commentId: string, state: ReviewState) => void;
  onStartEditing: (commentId: string, body: string) => void;
  onEditingBodyChange: (value: string) => void;
  onSaveEdit: (commentId: string) => void;
  onCancelEdit: () => void;
  onDeleteComment: (commentId: string) => void;
  threadActionLocalError: { commentId: string | null; message: string | null };
}

const reviewActions: ReviewState[] = ["accepted", "rejected", "uncertain"];

function renderAnchor(
  segment: TextSegment,
  children: ReactNode,
  isHovered: boolean,
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>,
  onHoverAnchor: (anchorId: string | null) => void,
): ReactNode {
  const allColors = [...new Set(segment.anchors.flatMap((item) => item.colors))];
  const primaryColor = allColors[0] ?? colorForCategory("human");
  const sharedSegment = segment.anchors.length > 1 || allColors.length > 1;
  const hoverAnchorId = segment.anchors.find((item) => item.anchor.id === segment.refAnchorIds[0])?.anchor.id
    ?? segment.anchors[0]?.anchor.id
    ?? null;
  const dataTestId = segment.refAnchorIds.length === 1 ? `anchor-${segment.refAnchorIds[0]}` : undefined;

  return (
    <span
      key={`${segment.startOffset}-${segment.endOffset}`}
      ref={(element) => {
        segment.refAnchorIds.forEach((anchorId) => {
          anchorRefs.current[anchorId] = element;
        });
      }}
      className={`${styles.anchorText} ${isHovered ? styles.anchorTextActive : ""}`}
      data-testid={dataTestId}
      data-anchor-count={segment.anchors.length}
      data-anchor-ids={segment.anchors.map((item) => item.anchor.id).join(" ")}
      tabIndex={0}
      onFocus={() => onHoverAnchor(hoverAnchorId)}
      onBlur={() => onHoverAnchor(null)}
      onMouseEnter={() => onHoverAnchor(hoverAnchorId)}
      onMouseLeave={() => onHoverAnchor(null)}
      style={{
        background: isHovered
          ? `color-mix(in srgb, ${primaryColor} 16%, rgba(120, 126, 134, 0.24))`
          : sharedSegment
            ? "rgba(111, 118, 126, 0.18)"
            : "rgba(111, 118, 126, 0.13)",
        borderBottom: `2px solid ${isHovered ? primaryColor : "rgba(88, 95, 103, 0.45)"}`,
        outline: isHovered ? `1px solid color-mix(in srgb, ${primaryColor} 44%, white)` : "1px solid transparent",
      }}
    >
      {children}
    </span>
  );
}

function wrapInlineMarks(content: ReactNode, marks: ArtifactInlineMark[], key: string): ReactNode {
  return marks.reduce<ReactNode>((wrapped, mark, index) => {
    const markKey = `${key}-${mark.kind}-${index}`;
    if (mark.kind === "strong") {
      return <strong key={markKey}>{wrapped}</strong>;
    }
    if (mark.kind === "emphasis") {
      return <em key={markKey}>{wrapped}</em>;
    }
    if (mark.kind === "code") {
      return (
        <code key={markKey} className={styles.inlineCode}>
          {wrapped}
        </code>
      );
    }
    if (mark.kind === "link" && mark.href && isSafeHref(mark.href)) {
      return (
        <a
          key={markKey}
          href={mark.href}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.inlineLink}
          onClick={(event) => event.stopPropagation()}
        >
          {wrapped}
        </a>
      );
    }
    return wrapped;
  }, content);
}

const MARK_ORDER: Record<ArtifactInlineMarkKind, number> = {
  emphasis: 0,
  strong: 1,
  code: 2,
  link: 3,
};

function buildTextSegments(
  block: ArtifactBlock,
  anchors: ArtifactAnchor[],
  anchorThreadMap: Map<string, AnchorThread>,
): TextSegment[] {
  const blockAnchors = anchors
    .flatMap((anchor) =>
      anchorSegments(anchor)
        .filter((segment) => segment.block_id === block.id)
        .map((segment) => ({
          anchor,
          segment,
          isPrimarySegment: anchorPrimarySegment(anchor).block_id === segment.block_id
            && anchorPrimarySegment(anchor).start_offset === segment.start_offset
            && anchorPrimarySegment(anchor).end_offset === segment.end_offset,
        })),
    )
    .sort((left, right) => {
      if (left.segment.start_offset !== right.segment.start_offset) {
        return left.segment.start_offset - right.segment.start_offset;
      }
      if (left.segment.end_offset !== right.segment.end_offset) {
        return left.segment.end_offset - right.segment.end_offset;
      }
      return left.anchor.id.localeCompare(right.anchor.id);
    });

  const boundaries = new Set<number>([0, block.text.length]);
  blockAnchors.forEach((anchor) => {
    boundaries.add(anchor.segment.start_offset);
    boundaries.add(anchor.segment.end_offset);
  });
  (block.marks ?? []).forEach((mark) => {
    boundaries.add(mark.start_offset);
    boundaries.add(mark.end_offset);
  });

  const orderedBoundaries = [...boundaries].sort((left, right) => left - right);
  const assignedRefAnchorIds = new Set<string>();
  const segments: TextSegment[] = [];
  for (let index = 0; index < orderedBoundaries.length - 1; index += 1) {
    const startOffset = orderedBoundaries[index];
    const endOffset = orderedBoundaries[index + 1];
    if (startOffset >= endOffset) {
      continue;
    }

    const activeMarks = (block.marks ?? [])
      .filter((mark) => mark.start_offset <= startOffset && mark.end_offset >= endOffset)
      .sort((left, right) => MARK_ORDER[left.kind] - MARK_ORDER[right.kind])
      .map((mark) => mark);
    const activeAnchors = blockAnchors
      .filter((anchor) => anchor.segment.start_offset <= startOffset && anchor.segment.end_offset >= endOffset)
      .map((anchor) => ({
        anchor: anchor.anchor,
        colors: anchorThreadMap.get(anchor.anchor.id)?.colors ?? [colorForCategory("human")],
        segment: anchor.segment,
        isPrimarySegment: anchor.isPrimarySegment,
      }));
    const refAnchorIds = activeAnchors
      .filter((item) => {
        if (!item.isPrimarySegment) {
          return false;
        }
        if (assignedRefAnchorIds.has(item.anchor.id)) {
          return false;
        }
        assignedRefAnchorIds.add(item.anchor.id);
        return true;
      })
      .map((item) => item.anchor.id);

    segments.push({
      startOffset,
      endOffset,
      text: block.text.slice(startOffset, endOffset),
      marks: activeMarks,
      anchors: activeAnchors,
      refAnchorIds,
    });
  }

  return segments;
}

function renderBlockText(
  block: ArtifactBlock,
  anchors: ArtifactAnchor[],
  anchorThreadMap: Map<string, AnchorThread>,
  hoveredAnchorId: string | null,
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>,
  onHoverAnchor: (anchorId: string | null) => void,
): ReactNode {
  const segments = buildTextSegments(block, anchors, anchorThreadMap);
  const renderedSegments = segments.map((segment) => {
    const key = `${block.id}-${segment.startOffset}-${segment.endOffset}`;
    const content = wrapInlineMarks(segment.text, segment.marks, key);
    if (segment.anchors.length === 0) {
      return { key, kind: "plain" as const, content: <span key={key}>{content}</span> };
    }
    return {
      key,
      kind: "anchored" as const,
      segment,
      content: <span key={key}>{content}</span>,
    };
  });

  const groups: Array<AnchorRenderGroup | PlainRenderGroup> = [];
  for (const item of renderedSegments) {
    if (item.kind === "plain") {
      groups.push({ kind: "plain", key: item.key, content: item.content });
      continue;
    }

    const previous = groups.at(-1);
    const previousIsGroup = previous?.kind === "group";
    const canMerge = previousIsGroup
      && areSameAnchorSet(previous.anchors, item.segment.anchors)
      && previous.endOffset === item.segment.startOffset;

    if (canMerge) {
      previous.endOffset = item.segment.endOffset;
      previous.refAnchorIds.push(...item.segment.refAnchorIds);
      previous.children.push(item.content);
      continue;
    }

    groups.push({
      kind: "group",
      key: item.key,
      startOffset: item.segment.startOffset,
      endOffset: item.segment.endOffset,
      anchors: item.segment.anchors,
      refAnchorIds: [...item.segment.refAnchorIds],
      children: [item.content],
    });
  }

  return groups.map((item) => {
    if (item.kind === "plain") {
      return item.content;
    }
    const mergedSegment: TextSegment = {
      startOffset: item.startOffset,
      endOffset: item.endOffset,
      text: block.text.slice(item.startOffset, item.endOffset),
      marks: [],
      anchors: item.anchors,
      refAnchorIds: item.refAnchorIds,
    };
    const isHovered = item.anchors.some((anchor) => anchor.anchor.id === hoveredAnchorId);
    return renderAnchor(
      mergedSegment,
      <>{item.children}</>,
      isHovered,
      anchorRefs,
      onHoverAnchor,
    );
  });
}

function areSameAnchorSet(left: SegmentAnchor[], right: SegmentAnchor[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((anchor, index) => anchor.anchor.id === right[index]?.anchor.id);
}

function resolveSelectionDraft(
  container: HTMLElement,
  selection: Selection | null,
  blockId: string,
): SelectionDraft | null {
  if (selection === null || selection.rangeCount === 0 || selection.isCollapsed) {
    return null;
  }

  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) {
    return null;
  }

  const selectedText = range.toString().trim();
  if (!selectedText) {
    return null;
  }

  const offsetRange = range.cloneRange();
  offsetRange.selectNodeContents(container);
  offsetRange.setEnd(range.startContainer, range.startOffset);
  const startOffset = offsetRange.toString().length;

  return {
    blockId,
    startOffset,
    endOffset: startOffset + selectedText.length,
    quote: selectedText,
  };
}

function ThreadCards({
  thread,
  activeDocumentRevisionId,
  hoveredAnchorId,
  commentRefs,
  replyDrafts,
  activeReplyComposerId,
  editingCommentId,
  editingBody,
  onHoverAnchor,
  onReplyDraftChange,
  onToggleReplyComposer,
  onAddReply,
  onDeleteReply,
  onReviewState,
  onStartEditing,
  onEditingBodyChange,
  onSaveEdit,
  onCancelEdit,
  onDeleteComment,
  threadActionLocalError,
}: {
  thread: ArtifactThread;
  activeDocumentRevisionId: string | null;
  hoveredAnchorId: string | null;
  commentRefs: MutableRefObject<Record<string, HTMLElement | null>>;
  replyDrafts: Record<string, string>;
  activeReplyComposerId: string | null;
  editingCommentId: string | null;
  editingBody: string;
  onHoverAnchor: (anchorId: string | null) => void;
  onReplyDraftChange: (commentId: string, value: string) => void;
  onToggleReplyComposer: (commentId: string) => void;
  onAddReply: (comment: ArtifactComment) => void;
  onDeleteReply: (replyId: string, commentId: string) => void;
  onReviewState: (commentId: string, state: ReviewState) => void;
  onStartEditing: (commentId: string, body: string) => void;
  onEditingBodyChange: (value: string) => void;
  onSaveEdit: (commentId: string) => void;
  onCancelEdit: () => void;
  onDeleteComment: (commentId: string) => void;
  threadActionLocalError: { commentId: string | null; message: string | null };
}) {
  const isHistoricalThread = activeDocumentRevisionId !== null
    && thread.document_revision_id !== undefined
    && thread.document_revision_id !== null
    && thread.document_revision_id !== activeDocumentRevisionId;
  return (
    <section
      className={`${styles.thread} ${hoveredAnchorId === thread.anchor.id ? styles.threadActive : ""}`}
      data-testid={`thread-${thread.anchor.id}`}
      onMouseEnter={() => onHoverAnchor(thread.anchor.id)}
      onMouseLeave={() => onHoverAnchor(null)}
    >
      <div className={styles.threadCards}>
        {thread.comments.map((comment) => {
          const isEditing = editingCommentId === comment.id;
          const isReplyComposerOpen = activeReplyComposerId === comment.id;
          const isAgentComment = comment.author_type === "agent";
          const isResearchComment = comment.category === "research";
          const isHistoricalComment = isHistoricalThread
            || (
              activeDocumentRevisionId !== null
              && comment.document_revision_id !== undefined
              && comment.document_revision_id !== null
              && comment.document_revision_id !== activeDocumentRevisionId
            );
          const factCheckDetails = comment.category === "fact_check" ? getFactCheckDetails(comment.metadata) : null;
          const factCheckSources = factCheckDetails === null
            ? []
            : dedupeStrings([...factCheckDetails.sourceLinks, ...(comment.sources ?? [])]);
          const commentLocalError = threadActionLocalError.commentId === comment.id
            ? threadActionLocalError.message
            : null;
          return (
            <article
              key={comment.id}
              ref={(element) => {
                commentRefs.current[comment.id] = element;
              }}
              className={styles.card}
              data-testid={`comment-${comment.id}`}
            >
              <div className={styles.cardHeader}>
                <span className={styles.pill} style={{ color: colorForCategory(comment.category) }}>
                  {comment.author_label}
                </span>
                <div className={styles.toolbarGroup}>
                  {isHistoricalComment ? <span className={styles.reviewBadge}>original draft</span> : null}
                  <span className={styles.reviewBadge}>{comment.review_state}</span>
                </div>
              </div>
              {isEditing ? (
                <div className={styles.inlineEditor}>
                  <textarea
                    className={styles.replyInput}
                    value={editingBody}
                    onChange={(event) => onEditingBodyChange(event.target.value)}
                    aria-label="Edit reviewer comment"
                  />
                  <div className={styles.toolbarGroup}>
                    <button className={styles.button} type="button" onClick={() => onSaveEdit(comment.id)}>
                      Save
                    </button>
                    <button className={styles.ghostButton} type="button" onClick={onCancelEdit}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <p className={styles.cardBody}>
                  {factCheckDetails !== null ? inlineUrlsToLinks(comment.body) : comment.body}
                </p>
              )}
              {factCheckDetails !== null ? (
                <div className={styles.factCheckDetails} data-testid={`fact-check-details-${comment.id}`}>
                  {factCheckDetails.claimText ? (
                    <div className={styles.factCheckClaim}>Claim: {factCheckDetails.claimText}</div>
                  ) : null}
                  {factCheckDetails.verdict ? (
                    <div className={styles.factCheckVerdict}>Verdict: {factCheckDetails.verdict}</div>
                  ) : null}
                  {factCheckDetails.evidenceSummary ? (
                    <p className={styles.factCheckEvidence}>{factCheckDetails.evidenceSummary}</p>
                  ) : null}
                  {factCheckSources.length > 0 ? (
                    <div className={styles.factCheckSources}>
                      <span className={styles.factCheckSourcesLabel}>Sources</span>
                      <ol className={styles.factCheckSourceList}>
                        {factCheckSources.map((url) => (
                          <li key={url}>
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={styles.factCheckSourceLink}
                              title={url}
                            >
                              {formatHostnameLabel(url)}
                            </a>
                          </li>
                        ))}
                      </ol>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {comment.suggestion ? <div className={styles.suggestion}>Suggestion: {comment.suggestion}</div> : null}
              {factCheckDetails === null && comment.sources && comment.sources.length > 0 ? (
                <div className={styles.sources}>
                  <span className={styles.sourcesLabel}>Sources:</span>
                  <ul className={styles.sourcesList}>
                    {comment.sources.map((url, i) => (
                      <li key={i}>
                        <a href={url} target="_blank" rel="noopener noreferrer" className={styles.sourceLink}>
                          {url}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {isAgentComment ? (
                <div className={styles.commentActionRow}>
                  {reviewActions.map((state) => (
                    <button
                      key={state}
                      data-testid={`review-state-${comment.id}-${state}`}
                      className={`${styles.stateButton} ${comment.review_state === state ? styles.stateButtonActive : ""}`}
                      type="button"
                      onClick={() => onReviewState(comment.id, state)}
                    >
                      {state === "accepted" ? "Accept" : state === "rejected" ? "Reject" : "Uncertain"}
                    </button>
                  ))}
                  <button
                    className={styles.commentActionButton}
                    data-testid={`reply-toggle-${comment.id}`}
                    type="button"
                    onClick={() => onToggleReplyComposer(comment.id)}
                  >
                    {isReplyComposerOpen ? (isResearchComment ? "Cancel follow-up" : "Cancel comment") : (isResearchComment ? "Ask follow-up" : "Add comment")}
                  </button>
                </div>
              ) : !isEditing ? (
                <div className={styles.toolbarGroup}>
                  <button
                    className={styles.ghostButton}
                    data-testid={`edit-comment-${comment.id}`}
                    type="button"
                    onClick={() => onStartEditing(comment.id, comment.body)}
                  >
                    Edit
                  </button>
                  <button
                    className={styles.iconButtonDanger}
                    data-testid={`delete-comment-${comment.id}`}
                    type="button"
                    aria-label="Delete comment"
                    onClick={() => onDeleteComment(comment.id)}
                  >
                    <TrashIcon />
                  </button>
                </div>
              ) : null}
              {commentLocalError ? (
                <p className={styles.importGuidance} data-testid={`thread-action-local-error-${comment.id}`} role="alert">
                  {commentLocalError}
                </p>
              ) : null}

              <div className={styles.replyList}>
                {comment.replies.map((reply) => (
                  <div key={reply.id} className={styles.reply}>
                    <div className={styles.replyHeader}>
                      <span className={styles.replyMeta}>{reply.author_label}</span>
                      {reply.author_type === "human" ? (
                        <button
                          className={styles.replyDeleteButton}
                          data-testid={`delete-reply-${reply.id}`}
                          type="button"
                          aria-label={`Delete reply by ${reply.author_label}`}
                          onClick={() => onDeleteReply(reply.id, comment.id)}
                        >
                          <TrashIcon />
                        </button>
                      ) : null}
                    </div>
                    <div>{reply.body}</div>
                  </div>
                ))}
              </div>

              <div className={styles.replyComposer}>
                {isReplyComposerOpen ? (
                  <div className={styles.inlineReplyComposer}>
                    <textarea
                      className={styles.replyInput}
                      data-testid={`reply-input-${comment.id}`}
                      value={replyDrafts[comment.id] ?? ""}
                      onChange={(event) => onReplyDraftChange(comment.id, event.target.value)}
                      placeholder={isResearchComment ? "Ask a follow-up question about this finding" : "Add a comment on this note"}
                    />
                    <button
                      className={styles.button}
                      data-testid={`reply-submit-${comment.id}`}
                      type="button"
                      onClick={() => onAddReply(comment)}
                    >
                      {isResearchComment ? "Save follow-up" : "Save comment"}
                    </button>
                  </div>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function sortComments(comments: ArtifactComment[]): ArtifactComment[] {
  return [...comments].sort((left, right) => {
    const createdAtDifference = new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
    if (createdAtDifference !== 0) {
      return createdAtDifference;
    }
    return left.id.localeCompare(right.id);
  });
}

interface FactCheckDetails {
  claimText: string;
  verdict: string;
  evidenceSummary: string;
  sourceLinks: string[];
}

const INLINE_URL_PATTERN = /https?:\/\/[^\s<>"']+/g;

function getFactCheckDetails(metadata: Record<string, unknown> | undefined): FactCheckDetails | null {
  if (metadata === undefined) {
    return null;
  }
  const claimText = typeof metadata.claim_text === "string" ? metadata.claim_text : "";
  const verdict = typeof metadata.verdict === "string" ? metadata.verdict.replaceAll("_", " ") : "";
  const evidenceSummary = typeof metadata.evidence_summary === "string" ? metadata.evidence_summary : "";
  const sourceLinks = dedupeStrings([
    ...extractStringArray(metadata.source_links),
    ...extractStringArray(metadata.official_source_links),
    ...extractStringArray(metadata.related_post_links),
  ]);
  if (!claimText && !verdict && !evidenceSummary && sourceLinks.length === 0) {
    return null;
  }
  return { claimText, verdict, evidenceSummary, sourceLinks };
}

function extractStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item)).filter((item) => item.length > 0);
}

function dedupeStrings(values: string[]): string[] {
  return [...new Set(values)];
}

function formatHostnameLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "") || url;
  } catch {
    return url;
  }
}

function splitTrailingUrlPunctuation(rawMatch: string): { url: string; suffix: string } {
  let url = rawMatch;
  let suffix = "";

  while (url.length > 0) {
    const trailingCharacter = url.at(-1);
    if (!trailingCharacter) {
      break;
    }
    if (/[.,;:!?]/.test(trailingCharacter)) {
      suffix = `${trailingCharacter}${suffix}`;
      url = url.slice(0, -1);
      continue;
    }
    if (trailingCharacter === ")") {
      const openParens = (url.match(/\(/g) ?? []).length;
      const closedParens = (url.match(/\)/g) ?? []).length;
      if (closedParens > openParens) {
        suffix = `${trailingCharacter}${suffix}`;
        url = url.slice(0, -1);
        continue;
      }
    }
    break;
  }

  return { url, suffix };
}

function inlineUrlsToLinks(body: string): ReactNode {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;

  for (const match of body.matchAll(INLINE_URL_PATTERN)) {
    const rawMatch = match[0];
    const startIndex = match.index ?? 0;
    if (startIndex > lastIndex) {
      nodes.push(body.slice(lastIndex, startIndex));
    }

    const { url, suffix } = splitTrailingUrlPunctuation(rawMatch);
    if (url.length > 0 && isSafeHref(url)) {
      nodes.push(
        <a
          key={`${url}-${startIndex}`}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.factCheckInlineLink}
          title={url}
          onClick={(event) => event.stopPropagation()}
        >
          {formatHostnameLabel(url)}
        </a>,
      );
      if (suffix.length > 0) {
        nodes.push(suffix);
      }
    } else {
      nodes.push(rawMatch);
    }

    lastIndex = startIndex + rawMatch.length;
  }

  if (lastIndex === 0) {
    return body;
  }

  if (lastIndex < body.length) {
    nodes.push(body.slice(lastIndex));
  }

  return nodes;
}

export function DocumentPane({
  document,
  anchors,
  threads,
  anchorThreadMap,
  activeDocumentRevisionId,
  selectionEnabled = true,
  hoveredAnchorId,
  hiddenBlockIds = [],
  previewPruningEnabled = false,
  anchorRefs,
  commentRefs,
  onHoverAnchor,
  onSelectionDraft,
  onHideBlock,
  onRestoreBlock,
  onRestoreAllBlocks,
  replyDrafts,
  activeReplyComposerId,
  editingCommentId,
  editingBody,
  onReplyDraftChange,
  onToggleReplyComposer,
  onAddReply,
  onDeleteReply,
  onReviewState,
  onStartEditing,
  onEditingBodyChange,
  onSaveEdit,
  onCancelEdit,
  onDeleteComment,
  threadActionLocalError,
}: DocumentPaneProps) {
  const hiddenBlockIdSet = useMemo(() => new Set(hiddenBlockIds), [hiddenBlockIds]);

  const blockThreads = useMemo(() => {
    const grouped = new Map<string, ArtifactThread[]>();
    threads.forEach((thread) => {
      const primarySegment = anchorPrimarySegment(thread.anchor);
      const existing = grouped.get(primarySegment.block_id) ?? [];
      existing.push({
        ...thread,
        comments: sortComments(thread.comments),
      });
      grouped.set(primarySegment.block_id, existing);
    });
    grouped.forEach((value, key) => {
      value.sort((left, right) => {
        const leftPrimarySegment = anchorPrimarySegment(left.anchor);
        const rightPrimarySegment = anchorPrimarySegment(right.anchor);
        if (leftPrimarySegment.start_offset !== rightPrimarySegment.start_offset) {
          return leftPrimarySegment.start_offset - rightPrimarySegment.start_offset;
        }
        if (leftPrimarySegment.end_offset !== rightPrimarySegment.end_offset) {
          return leftPrimarySegment.end_offset - rightPrimarySegment.end_offset;
        }
        return left.anchor.id.localeCompare(right.anchor.id);
      });
      grouped.set(key, value);
    });
    return grouped;
  }, [threads]);

  return (
    <div className={styles.documentPane}>
      <div className={styles.sectionTitle}>Text under review</div>
      <h2 className={styles.documentTitle} data-testid="document-title">{document?.title ?? "No document loaded"}</h2>
      {previewPruningEnabled && hiddenBlockIds.length > 0 ? (
        <div className={styles.previewControls}>
          <div className={styles.previewSummary}>
            <span className={styles.previewBadge}>Preview edit</span>
            <span className={styles.previewNote}>
              {hiddenBlockIds.length} hidden {hiddenBlockIds.length === 1 ? "block" : "blocks"} excluded from this run.
            </span>
          </div>
          <button
            className={styles.ghostButton}
            type="button"
            data-testid="restore-all-preview-blocks"
            onClick={onRestoreAllBlocks}
          >
            Restore all
          </button>
        </div>
      ) : null}
      {document?.blocks.length ? (
        document.blocks.map((block) => (
          (() => {
            const isPreviewHidden = hiddenBlockIdSet.has(block.id);
            return (
              <div
                key={block.id}
                className={styles.paragraphRow}
                data-testid={`document-block-${block.index}`}
              >
                <div
                  className={`${styles.documentBlock} ${
                    block.origin === "synthetic_unmatched"
                      ? styles.documentBlockSynthetic
                      : ""
                  } ${
                    block.kind === "heading"
                      ? styles.documentBlockHeading
                      : block.kind === "code"
                        ? styles.documentBlockCode
                        : styles.paragraph
                  } ${isPreviewHidden ? styles.previewBlockMuted : ""}`}
                  data-block-id={block.id}
                  data-block-origin={block.origin ?? "source"}
                  data-preview-hidden={isPreviewHidden ? "true" : "false"}
                  onMouseUp={(event) => {
                    if (!selectionEnabled) {
                      return;
                    }
                    const draft = resolveSelectionDraft(event.currentTarget, window.getSelection(), block.id);
                    onSelectionDraft(draft);
                  }}
                >
                  {block.kind === "heading" ? (
                    block.level === 1 ? (
                      <h1 className={styles.headingLevel1}>
                        {renderBlockText(block, anchors, anchorThreadMap, hoveredAnchorId, anchorRefs, onHoverAnchor)}
                      </h1>
                    ) : block.level === 2 ? (
                      <h2 className={styles.headingLevel2}>
                        {renderBlockText(block, anchors, anchorThreadMap, hoveredAnchorId, anchorRefs, onHoverAnchor)}
                      </h2>
                    ) : (
                      <h3 className={styles.headingLevel3}>
                        {renderBlockText(block, anchors, anchorThreadMap, hoveredAnchorId, anchorRefs, onHoverAnchor)}
                      </h3>
                    )
                  ) : block.kind === "code" ? (
                    <pre className={styles.codeBlock}>
                      <code>{renderBlockText(block, anchors, anchorThreadMap, hoveredAnchorId, anchorRefs, onHoverAnchor)}</code>
                    </pre>
                  ) : (
                    renderBlockText(block, anchors, anchorThreadMap, hoveredAnchorId, anchorRefs, onHoverAnchor)
                  )}
                </div>
                <div className={styles.paragraphComments}>
                  {previewPruningEnabled ? (
                    <div className={styles.previewBlockActions}>
                      <button
                        className={`${styles.ghostButton} ${isPreviewHidden ? styles.previewRestoreButton : ""}`}
                        type="button"
                        data-testid={isPreviewHidden ? `restore-preview-block-${block.id}` : `hide-preview-block-${block.id}`}
                        onClick={() => (isPreviewHidden ? onRestoreBlock(block.id) : onHideBlock(block.id))}
                      >
                        {isPreviewHidden ? "Restore section" : "Remove section"}
                      </button>
                    </div>
                  ) : null}
                  {(blockThreads.get(block.id) ?? []).length ? (
                    (blockThreads.get(block.id) ?? []).map((thread) => (
                      <ThreadCards
                        key={thread.anchor.id}
                        thread={thread}
                        activeDocumentRevisionId={activeDocumentRevisionId}
                        hoveredAnchorId={hoveredAnchorId}
                        commentRefs={commentRefs}
                        replyDrafts={replyDrafts}
                        activeReplyComposerId={activeReplyComposerId}
                        editingCommentId={editingCommentId}
                        editingBody={editingBody}
                        onHoverAnchor={onHoverAnchor}
                        onReplyDraftChange={onReplyDraftChange}
                        onToggleReplyComposer={onToggleReplyComposer}
                        onAddReply={onAddReply}
                        onDeleteReply={onDeleteReply}
                        onReviewState={onReviewState}
                        onStartEditing={onStartEditing}
                        onEditingBodyChange={onEditingBodyChange}
                        onSaveEdit={onSaveEdit}
                        onCancelEdit={onCancelEdit}
                        onDeleteComment={onDeleteComment}
                        threadActionLocalError={threadActionLocalError}
                      />
                    ))
                  ) : (
                    <div className={styles.paragraphCommentsSpacer} aria-hidden="true" />
                  )}
                </div>
              </div>
            );
          })()
        ))
      ) : (
        <div className={styles.emptyState}>Submit a URL, pasted draft, or text file to start the review.</div>
      )}
    </div>
  );
}

function isSafeHref(href: string): boolean {
  const value = href.trim().toLowerCase();
  return !(value.startsWith("javascript:") || value.startsWith("data:"));
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
      <path
        d="M6 2.5h4l.5 1H13v1H3v-1h2.5l.5-1Zm-1 3h1v6H5v-6Zm3 0h1v6H8v-6Zm3 0h-1v6h1v-6ZM4.5 5h7l-.4 7.1a1 1 0 0 1-1 .9H5.9a1 1 0 0 1-1-.9L4.5 5Z"
        fill="currentColor"
      />
    </svg>
  );
}
