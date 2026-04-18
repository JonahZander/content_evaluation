import styles from "@/components/ReviewWorkbench.module.css";
import type { SelectionDraft } from "@/lib/types";

const REVIEW_INTERACTIONS_LOCKED_TITLE = "Comment edits are paused while revised markdown is in progress.";

interface SelectionBannerProps {
  selectionDraft: SelectionDraft | null;
  commentDraft: string;
  locked?: boolean;
  localErrorMessage: string | null;
  onCommentDraftChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

export function SelectionBanner({
  selectionDraft,
  commentDraft,
  locked = false,
  localErrorMessage,
  onCommentDraftChange,
  onSave,
  onCancel,
}: SelectionBannerProps) {
  if (!selectionDraft) {
    return null;
  }

  return (
    <section className={styles.selectionBanner}>
      <strong>Create a reviewer comment</strong>
      <p className={styles.selectionQuote}>“{selectionDraft.quote}”</p>
      <div className={styles.replyComposer}>
        <textarea
          className={styles.toolbarTextarea}
          data-testid="selection-comment-input"
          value={commentDraft}
          disabled={locked}
          onChange={(event) => onCommentDraftChange(event.target.value)}
          placeholder="Add a reviewer note for this selection"
        />
        {localErrorMessage ? (
          <p className={styles.importGuidance} data-testid="selection-comment-local-error" role="alert">
            {localErrorMessage}
          </p>
        ) : null}
        <div className={styles.toolbarGroup}>
          <button
            className={styles.button}
            data-testid="selection-comment-save"
            type="button"
            disabled={locked}
            title={locked ? REVIEW_INTERACTIONS_LOCKED_TITLE : undefined}
            onClick={onSave}
          >
            Save comment
          </button>
          <button className={styles.ghostButton} type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </section>
  );
}
