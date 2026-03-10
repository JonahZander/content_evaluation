import styles from "@/components/ReviewWorkbench.module.css";

interface FormState {
  sourceType: "url" | "text" | "file";
  title: string;
  sourceLabel: string;
  text: string;
  url: string;
}

interface ReviewToolbarProps {
  formState: FormState;
  fileInputKey: number;
  selectedFile: File | null;
  statusMessage: string;
  submitting: boolean;
  onFormChange: (updater: (current: FormState) => FormState) => void;
  onFileChange: (file: File | null) => void;
  onSubmit: () => void;
  onExport: (format: "md" | "json") => void;
}

export function ReviewToolbar({
  formState,
  fileInputKey,
  selectedFile,
  statusMessage,
  submitting,
  onFormChange,
  onFileChange,
  onSubmit,
  onExport,
}: ReviewToolbarProps) {
  return (
    <section className={styles.toolbar}>
      <div className={styles.toolbarGroup}>
        <select
          className={styles.toolbarSelect}
          value={formState.sourceType}
          onChange={(event) =>
            onFormChange((current) => ({
              ...current,
              sourceType: event.target.value as FormState["sourceType"],
            }))
          }
        >
          <option value="text">Pasted text</option>
          <option value="url">URL</option>
          <option value="file">Text file</option>
        </select>
        <input
          className={styles.toolbarInput}
          value={formState.title}
          onChange={(event) => onFormChange((current) => ({ ...current, title: event.target.value }))}
          placeholder="Draft title"
        />
        {formState.sourceType === "url" ? (
          <input
            className={styles.toolbarInput}
            value={formState.url}
            onChange={(event) =>
              onFormChange((current) => ({
                ...current,
                url: event.target.value,
                sourceLabel: event.target.value,
              }))
            }
            placeholder="https://example.com/post"
          />
        ) : null}
        {formState.sourceType === "file" ? (
          <div className={styles.fileInputWrap}>
            <input
              key={fileInputKey}
              className={styles.toolbarInput}
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
            {selectedFile ? <span className={styles.fileMeta}>{selectedFile.name}</span> : null}
          </div>
        ) : (
          <textarea
            className={styles.toolbarTextarea}
            value={formState.text}
            onChange={(event) => onFormChange((current) => ({ ...current, text: event.target.value }))}
            placeholder="Paste draft text"
          />
        )}
      </div>
      <div className={styles.toolbarGroup}>
        <button className={styles.button} type="button" onClick={onSubmit} disabled={submitting}>
          {submitting ? "Submitting..." : "Analyze content"}
        </button>
        <button className={styles.ghostButton} type="button" onClick={() => onExport("md")}>
          Export Markdown
        </button>
        <button className={styles.ghostButton} type="button" onClick={() => onExport("json")}>
          Export JSON
        </button>
        <span className={styles.statusPill} role="status">
          {statusMessage}
        </span>
      </div>
    </section>
  );
}
