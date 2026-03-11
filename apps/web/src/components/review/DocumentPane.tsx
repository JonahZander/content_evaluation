import { useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { ConnectorCanvas } from "@/components/review/ConnectorCanvas";
import { categoryColors, colorForCategory } from "@/components/review/category-colors";
import type {
  ArtifactAnchor,
  ArtifactBlock,
  ArtifactComment,
  ArtifactDocument,
  ArtifactInlineMark,
  ArtifactInlineMarkKind,
  ArtifactThread,
  ReviewState,
} from "@/lib/types";

interface AnchorThread {
  colors: string[];
}

interface SelectionDraft {
  blockId: string;
  startOffset: number;
  endOffset: number;
  quote: string;
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
  onReviewState: (commentId: string, state: ReviewState) => void;
  onStartEditing: (commentId: string, body: string) => void;
  onEditingBodyChange: (value: string) => void;
  onSaveEdit: (commentId: string) => void;
  onCancelEdit: () => void;
  onDeleteComment: (commentId: string) => void;
}

const reviewActions: ReviewState[] = ["accepted", "rejected", "uncertain"];

function renderAnchor(
  anchor: ArtifactAnchor,
  children: ReactNode,
  colors: string[],
  isHovered: boolean,
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>,
  onHoverAnchor: (anchorId: string | null) => void,
): ReactNode {
  const gradient =
    colors.length === 1
      ? `color-mix(in srgb, ${colors[0]} 18%, white)`
      : `linear-gradient(90deg, ${colors
          .map((color, index) => `${color} ${index * (100 / colors.length)}% ${(index + 1) * (100 / colors.length)}%`)
          .join(", ")})`;

  return (
    <span
      key={anchor.id}
      ref={(element) => {
        anchorRefs.current[anchor.id] = element;
      }}
      className={`${styles.anchorText} ${isHovered ? styles.anchorTextActive : ""}`}
      data-testid={`anchor-${anchor.id}`}
      tabIndex={0}
      onFocus={() => onHoverAnchor(anchor.id)}
      onBlur={() => onHoverAnchor(null)}
      onMouseEnter={() => onHoverAnchor(anchor.id)}
      onMouseLeave={() => onHoverAnchor(null)}
      style={{
        background: colors.length === 1 ? gradient : "rgba(255, 247, 236, 0.9)",
        boxShadow:
          colors.length > 1
            ? `inset 0 0 0 1px rgba(0,0,0,0.04), inset 6px 0 0 0 ${colors[0]}`
            : undefined,
        borderBottom: `2px solid ${colors[0]}`,
      }}
    >
      {children}
    </span>
  );
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

function renderMarkedRange(block: ArtifactBlock, startOffset: number, endOffset: number, keyPrefix: string): ReactNode[] {
  if (startOffset >= endOffset) {
    return [];
  }

  const marks = (block.marks ?? []).filter(
    (mark) => mark.start_offset < endOffset && mark.end_offset > startOffset,
  );
  if (marks.length === 0) {
    return [block.text.slice(startOffset, endOffset)];
  }

  const boundaries = new Set<number>([startOffset, endOffset]);
  marks.forEach((mark) => {
    boundaries.add(Math.max(startOffset, mark.start_offset));
    boundaries.add(Math.min(endOffset, mark.end_offset));
  });

  const orderedBoundaries = [...boundaries].sort((left, right) => left - right);
  const fragments: ReactNode[] = [];
  for (let index = 0; index < orderedBoundaries.length - 1; index += 1) {
    const segmentStart = orderedBoundaries[index];
    const segmentEnd = orderedBoundaries[index + 1];
    if (segmentStart === segmentEnd) {
      continue;
    }
    const text = block.text.slice(segmentStart, segmentEnd);
    const activeMarks = marks
      .filter((mark) => mark.start_offset <= segmentStart && mark.end_offset >= segmentEnd)
      .sort((left, right) => MARK_ORDER[left.kind] - MARK_ORDER[right.kind])
      .map((mark) => mark.kind);
    fragments.push(wrapInlineMarks(text, activeMarks, `${keyPrefix}-${segmentStart}-${segmentEnd}`));
  }
  return fragments;
}

const MARK_ORDER: Record<ArtifactInlineMarkKind, number> = {
  emphasis: 0,
  strong: 1,
  code: 2,
};

function renderBlockText(
  block: ArtifactBlock,
  anchors: ArtifactAnchor[],
  anchorThreadMap: Map<string, AnchorThread>,
  hoveredAnchorId: string | null,
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>,
  onHoverAnchor: (anchorId: string | null) => void,
): ReactNode {
  const blockAnchors = anchors
    .filter((anchor) => anchor.block_id === block.id)
    .sort((left, right) => left.start_offset - right.start_offset);

  if (blockAnchors.length === 0) {
    return renderMarkedRange(block, 0, block.text.length, `${block.id}-plain`);
  }

  const fragments: ReactNode[] = [];
  let cursor = 0;
  blockAnchors.forEach((anchor) => {
    if (cursor < anchor.start_offset) {
      fragments.push(...renderMarkedRange(block, cursor, anchor.start_offset, `${block.id}-before-${cursor}`));
    }
    const colors = anchorThreadMap.get(anchor.id)?.colors ?? [colorForCategory("human")];
    fragments.push(
      renderAnchor(
        anchor,
        renderMarkedRange(block, anchor.start_offset, anchor.end_offset, `${block.id}-anchor-${anchor.id}`),
        colors,
        hoveredAnchorId === anchor.id,
        anchorRefs,
        onHoverAnchor,
      ),
    );
    cursor = anchor.end_offset;
  });
  if (cursor < block.text.length) {
    fragments.push(...renderMarkedRange(block, cursor, block.text.length, `${block.id}-after-${cursor}`));
  }
  return fragments;
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
                    <span className={styles.replyMeta}>{reply.author_label}</span>
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
      const existing = grouped.get(thread.anchor.block_id) ?? [];
      existing.push({
        ...thread,
        comments: sortComments(thread.comments),
      });
      grouped.set(thread.anchor.block_id, existing);
    });
    grouped.forEach((value, key) => {
      value.sort((left, right) => {
        if (left.anchor.start_offset !== right.anchor.start_offset) {
          return left.anchor.start_offset - right.anchor.start_offset;
        }
        if (left.anchor.end_offset !== right.anchor.end_offset) {
          return left.anchor.end_offset - right.anchor.end_offset;
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
                block.kind === "heading"
                  ? styles.documentBlockHeading
                  : block.kind === "code"
                    ? styles.documentBlockCode
                    : styles.paragraph
              }`}
              data-block-id={block.id}
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
