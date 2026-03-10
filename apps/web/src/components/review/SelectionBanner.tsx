import styles from "@/components/ReviewWorkbench.module.css";

interface SelectionDraft {
  blockId: string;
  startOffset: number;
  endOffset: number;
  quote: string;
}

interface SelectionBannerProps {
  selectionDraft: SelectionDraft | null;
  commentDraft: string;
  onCommentDraftChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

export function SelectionBanner({
  selectionDraft,
  commentDraft,
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
          onChange={(event) => onCommentDraftChange(event.target.value)}
          placeholder="Add a reviewer note for this selection"
        />
        <div className={styles.toolbarGroup}>
          <button className={styles.button} data-testid="selection-comment-save" type="button" onClick={onSave}>
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
