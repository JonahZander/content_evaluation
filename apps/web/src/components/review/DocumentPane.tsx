import { useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { ConnectorCanvas } from "@/components/review/ConnectorCanvas";
import { categoryColors, colorForCategory } from "@/components/review/category-colors";
import {
  anchorPrimarySegment,
  anchorSegments,
  type ArtifactAnchorSegment,
  type ArtifactAnchor,
  type ArtifactBlock,
  type ArtifactComment,
  type ArtifactDocument,
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
  marks: ArtifactInlineMarkKind[];
  anchors: SegmentAnchor[];
  refAnchorIds: string[];
}

interface DocumentPaneProps {
  document: ArtifactDocument | null;
  anchors: ArtifactAnchor[];
  threads: ArtifactThread[];
  anchorThreadMap: Map<string, AnchorThread>;
  selectionEnabled?: boolean;
  hoveredAnchorId: string | null;
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>;
  commentRefs: MutableRefObject<Record<string, HTMLElement | null>>;
  onHoverAnchor: (anchorId: string | null) => void;
  onSelectionDraft: (draft: SelectionDraft | null) => void;
  replyDrafts: Record<string, string>;
  editingCommentId: string | null;
  editingBody: string;
  onReplyDraftChange: (commentId: string, value: string) => void;
  onAddReply: (commentId: string) => void;
  onDeleteReply: (replyId: string) => void;
  onReviewState: (commentId: string, state: ReviewState) => void;
  onStartEditing: (commentId: string, body: string) => void;
  onEditingBodyChange: (value: string) => void;
  onSaveEdit: (commentId: string) => void;
  onCancelEdit: () => void;
  onDeleteComment: (commentId: string) => void;
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
  const railWidth = Math.max(8, allColors.length * 4);
  const background = sharedSegment
    ? `linear-gradient(90deg, ${buildRailStops(allColors, railWidth)}, rgba(255, 247, 236, 0.92) ${railWidth}px 100%)`
    : `color-mix(in srgb, ${primaryColor} 18%, white)`;
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
        background,
        boxShadow:
          sharedSegment
            ? `inset 0 0 0 1px rgba(0,0,0,0.04), inset ${railWidth}px 0 0 rgba(0,0,0,0)`
            : undefined,
        borderBottom: `2px solid ${primaryColor}`,
      }}
    >
      {children}
    </span>
  );
}

function buildRailStops(colors: string[], railWidth: number): string {
  const stripeWidth = railWidth / Math.max(colors.length, 1);
  return colors
    .map((color, index) => `${color} ${index * stripeWidth}px ${(index + 1) * stripeWidth}px`)
    .join(", ");
}

function wrapInlineMarks(content: ReactNode, marks: ArtifactInlineMarkKind[], key: string): ReactNode {
  return marks.reduce<ReactNode>((wrapped, kind, index) => {
    const markKey = `${key}-${kind}-${index}`;
    if (kind === "strong") {
      return <strong key={markKey}>{wrapped}</strong>;
    }
    if (kind === "emphasis") {
      return <em key={markKey}>{wrapped}</em>;
    }
    if (kind === "code") {
      return (
        <code key={markKey} className={styles.inlineCode}>
          {wrapped}
        </code>
      );
    }
    return wrapped;
  }, content);
}

const MARK_ORDER: Record<ArtifactInlineMarkKind, number> = {
  emphasis: 0,
  strong: 1,
  code: 2,
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
      .map((mark) => mark.kind);
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
  return segments.map((segment) => {
    const key = `${block.id}-${segment.startOffset}-${segment.endOffset}`;
    const content = wrapInlineMarks(
      segment.text,
      segment.marks,
      key,
    );
    if (segment.anchors.length === 0) {
      return <span key={key}>{content}</span>;
    }
    const isHovered = segment.anchors.some((item) => item.anchor.id === hoveredAnchorId);
    return renderAnchor(segment, content, isHovered, anchorRefs, onHoverAnchor);
  });
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
  hoveredAnchorId,
  commentRefs,
  replyDrafts,
  editingCommentId,
  editingBody,
  onHoverAnchor,
  onReplyDraftChange,
  onAddReply,
  onDeleteReply,
  onReviewState,
  onStartEditing,
  onEditingBodyChange,
  onSaveEdit,
  onCancelEdit,
  onDeleteComment,
}: {
  thread: ArtifactThread;
  hoveredAnchorId: string | null;
  commentRefs: MutableRefObject<Record<string, HTMLElement | null>>;
  replyDrafts: Record<string, string>;
  editingCommentId: string | null;
  editingBody: string;
  onHoverAnchor: (anchorId: string | null) => void;
  onReplyDraftChange: (commentId: string, value: string) => void;
  onAddReply: (commentId: string) => void;
  onDeleteReply: (replyId: string) => void;
  onReviewState: (commentId: string, state: ReviewState) => void;
  onStartEditing: (commentId: string, body: string) => void;
  onEditingBodyChange: (value: string) => void;
  onSaveEdit: (commentId: string) => void;
  onCancelEdit: () => void;
  onDeleteComment: (commentId: string) => void;
}) {
  return (
    <section
      className={`${styles.thread} ${hoveredAnchorId === thread.anchor.id ? styles.threadActive : ""}`}
      data-testid={`thread-${thread.anchor.id}`}
      onMouseEnter={() => onHoverAnchor(thread.anchor.id)}
      onMouseLeave={() => onHoverAnchor(null)}
    >
      <div className={styles.threadHeader}>
        <strong>Linked section</strong>
        <span className={styles.threadQuote}>{thread.anchor.quote}</span>
      </div>
      <div className={styles.threadCards}>
        {thread.comments.map((comment) => {
          const isEditing = editingCommentId === comment.id;
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
                <span className={styles.pill}>{comment.category.replace("_", " ")}</span>
                <span className={styles.reviewBadge}>{comment.review_state}</span>
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
                <p className={styles.cardBody}>{comment.body}</p>
              )}
              {comment.suggestion ? <div className={styles.suggestion}>Suggestion: {comment.suggestion}</div> : null}
              {comment.author_type === "agent" ? (
                <div className={styles.toolbarGroup}>
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
                    className={styles.ghostButton}
                    data-testid={`delete-comment-${comment.id}`}
                    type="button"
                    onClick={() => onDeleteComment(comment.id)}
                  >
                    Delete
                  </button>
                </div>
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
                          onClick={() => onDeleteReply(reply.id)}
                        >
                          x
                        </button>
                      ) : null}
                    </div>
                    <div>{reply.body}</div>
                  </div>
                ))}
              </div>

              <div className={styles.replyComposer}>
                <textarea
                  className={styles.replyInput}
                  data-testid={`reply-input-${comment.id}`}
                  value={replyDrafts[comment.id] ?? ""}
                  onChange={(event) => onReplyDraftChange(comment.id, event.target.value)}
                  placeholder="Reply to this comment"
                />
                <button
                  className={styles.button}
                  data-testid={`reply-submit-${comment.id}`}
                  type="button"
                  onClick={() => onAddReply(comment.id)}
                >
                  Add reply
                </button>
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

export function DocumentPane({
  document,
  anchors,
  threads,
  anchorThreadMap,
  selectionEnabled = true,
  hoveredAnchorId,
  anchorRefs,
  commentRefs,
  onHoverAnchor,
  onSelectionDraft,
  replyDrafts,
  editingCommentId,
  editingBody,
  onReplyDraftChange,
  onAddReply,
  onDeleteReply,
  onReviewState,
  onStartEditing,
  onEditingBodyChange,
  onSaveEdit,
  onCancelEdit,
  onDeleteComment,
}: DocumentPaneProps) {
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [pathsByBlockId, setPathsByBlockId] = useState<Record<string, Array<{ id: string; path: string; color: string }>>>({});

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

  useEffect(() => {
    if (!document) {
      setPathsByBlockId({});
      return;
    }

    const updatePaths = () => {
      const nextPathsByBlockId: Record<string, Array<{ id: string; path: string; color: string }>> = {};

      document.blocks.forEach((block) => {
        const row = rowRefs.current[block.id];
        const rowThreads = blockThreads.get(block.id) ?? [];
        if (!row || rowThreads.length === 0) {
          return;
        }

        const rowRect = row.getBoundingClientRect();
        nextPathsByBlockId[block.id] = rowThreads.flatMap((thread) => {
          const anchorElement = anchorRefs.current[thread.anchor.id];
          if (!anchorElement) {
            return [];
          }
          const anchorRect = anchorElement.getBoundingClientRect();
          const startX = anchorRect.right - rowRect.left;
          const startY = anchorRect.top - rowRect.top + anchorRect.height / 2;

          return thread.comments.flatMap((comment) => {
            const commentElement = commentRefs.current[comment.id];
            if (!commentElement) {
              return [];
            }
            const commentRect = commentElement.getBoundingClientRect();
            const endX = commentRect.left - rowRect.left;
            const endY = commentRect.top - rowRect.top + commentRect.height / 2;
            const controlOffset = Math.max(32, (endX - startX) / 2);
            return {
              id: comment.id,
              color: categoryColors[comment.category] ?? "var(--ink)",
              path: `M ${startX} ${startY} C ${startX + controlOffset} ${startY}, ${endX - controlOffset} ${endY}, ${endX} ${endY}`,
            };
          });
        });
      });

      setPathsByBlockId(nextPathsByBlockId);
    };

    updatePaths();
    window.addEventListener("resize", updatePaths);
    return () => window.removeEventListener("resize", updatePaths);
  }, [anchorRefs, commentRefs, blockThreads, document]);

  return (
    <div className={styles.documentPane}>
      <div className={styles.sectionTitle}>Text under review</div>
      <h2 className={styles.documentTitle}>{document?.title ?? "No document loaded"}</h2>
      {document?.blocks.length ? (
        document.blocks.map((block) => (
          <div
            key={block.id}
            ref={(element) => {
              rowRefs.current[block.id] = element;
            }}
            className={styles.paragraphRow}
            data-testid={`document-block-${block.index}`}
          >
            <ConnectorCanvas paths={pathsByBlockId[block.id] ?? []} />
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
              }`}
              data-block-id={block.id}
              data-block-origin={block.origin ?? "source"}
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
              {(blockThreads.get(block.id) ?? []).length ? (
                (blockThreads.get(block.id) ?? []).map((thread) => (
                  <ThreadCards
                    key={thread.anchor.id}
                    thread={thread}
                    hoveredAnchorId={hoveredAnchorId}
                    commentRefs={commentRefs}
                    replyDrafts={replyDrafts}
                    editingCommentId={editingCommentId}
                    editingBody={editingBody}
                    onHoverAnchor={onHoverAnchor}
                    onReplyDraftChange={onReplyDraftChange}
                    onAddReply={onAddReply}
                    onDeleteReply={onDeleteReply}
                    onReviewState={onReviewState}
                    onStartEditing={onStartEditing}
                    onEditingBodyChange={onEditingBodyChange}
                    onSaveEdit={onSaveEdit}
                    onCancelEdit={onCancelEdit}
                    onDeleteComment={onDeleteComment}
                  />
                ))
              ) : (
                <div className={styles.paragraphCommentsSpacer} aria-hidden="true" />
              )}
            </div>
          </div>
        ))
      ) : (
        <div className={styles.emptyState}>Submit a URL, pasted draft, or text file to start the review.</div>
      )}
    </div>
  );
}
