import type { MutableRefObject } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { colorForCategory } from "@/components/review/category-colors";
import type { ArtifactEvent, ArtifactThread, ReviewState } from "@/lib/types";

interface CommentRailProps {
  threads: ArtifactThread[];
  events: ArtifactEvent[];
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
}

const reviewActions: ReviewState[] = ["accepted", "rejected", "uncertain"];

export function CommentRail({
  threads,
  events,
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
}: CommentRailProps) {
  return (
    <aside className={styles.commentPane}>
      <div className={styles.sectionTitle}>Comment rail</div>
      {threads.length ? (
        threads.map((thread) => (
          <section
            key={thread.anchor.id}
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
                    {comment.suggestion ? (
                      <div className={styles.suggestion}>Suggestion: {comment.suggestion}</div>
                    ) : null}
                    {comment.author_type === "agent" ? (
                      <div className={styles.toolbarGroup}>
                        {reviewActions.map((state) => (
                          <button
                            key={state}
                            data-testid={`review-state-${comment.id}-${state}`}
                            className={`${styles.stateButton} ${
                              comment.review_state === state ? styles.stateButtonActive : ""
                            }`}
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
        ))
      ) : (
        <section className={styles.emptyState}>
          Agent findings and reviewer comments will appear here after the first analysis run.
        </section>
      )}

      <section className={styles.eventPanel}>
        <div className={styles.sectionTitle}>Run log</div>
        {events.length ? (
          events.map((event) => (
            <div key={event.id} className={styles.eventItem}>
              <div>
                <strong>{event.stage}</strong>
                <div>{event.message}</div>
              </div>
              <div className={styles.eventMeta}>
                {event.agent_name ?? "system"}
                <br />
                {event.model_name ?? "n/a"}
              </div>
            </div>
          ))
        ) : (
          <div className={styles.emptyEventState}>No run events yet.</div>
        )}
      </section>
    </aside>
  );
}
