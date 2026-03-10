import styles from "@/components/ReviewWorkbench.module.css";
import type { AgentCatalogEntry, PersistenceMode } from "@/lib/types";

export interface ReviewFormState {
  sourceType: "url" | "text" | "file";
  title: string;
  sourceLabel: string;
  text: string;
  url: string;
  persistenceMode: PersistenceMode;
  includeDebugTrace: boolean;
  selectedAgents: string[];
}

interface ReviewToolbarProps {
  formState: ReviewFormState;
  agents: AgentCatalogEntry[];
  fileInputKey: number;
  selectedFile: File | null;
  statusMessage: string;
  submitting: boolean;
  importInputKey: number;
  onFormChange: (updater: (current: ReviewFormState) => ReviewFormState) => void;
  onFileChange: (file: File | null) => void;
  onImportFileChange: (file: File | null) => void;
  onSubmit: () => void;
  onExport: (format: "md" | "json") => void;
}

export function ReviewToolbar({
  formState,
  agents,
  fileInputKey,
  selectedFile,
  statusMessage,
  submitting,
  importInputKey,
  onFormChange,
  onFileChange,
  onImportFileChange,
  onSubmit,
  onExport,
}: ReviewToolbarProps) {
  return (
    <section className={styles.toolbar}>
      <div className={styles.toolbarGroup}>
        <select
          className={styles.toolbarSelect}
          data-testid="source-type-select"
          value={formState.sourceType}
          onChange={(event) =>
            onFormChange((current) => ({
              ...current,
              sourceType: event.target.value as ReviewFormState["sourceType"],
            }))
          }
        >
          <option value="text">Pasted text</option>
          <option value="url">URL</option>
          <option value="file">Text file</option>
        </select>
        <input
          className={styles.toolbarInput}
          data-testid="draft-title-input"
          value={formState.title}
          onChange={(event) => onFormChange((current) => ({ ...current, title: event.target.value }))}
          placeholder="Draft title"
        />
        <select
          className={styles.toolbarSelect}
          data-testid="persistence-mode-select"
          value={formState.persistenceMode}
          onChange={(event) =>
            onFormChange((current) => ({
              ...current,
              persistenceMode: event.target.value as PersistenceMode,
            }))
          }
        >
          <option value="session">Session mode</option>
          <option value="workspace">Workspace mode</option>
        </select>
        <label className={styles.toggleLabel}>
          <input
            data-testid="debug-trace-toggle"
            type="checkbox"
            checked={formState.includeDebugTrace}
            onChange={(event) =>
              onFormChange((current) => ({
                ...current,
                includeDebugTrace: event.target.checked,
              }))
            }
          />
          Include debug trace
        </label>
      </div>

      <div className={styles.agentSelector}>
        {agents.map((agent) => {
          const checked = formState.selectedAgents.includes(agent.agent_id);
          return (
            <label key={agent.agent_id} className={styles.agentChip}>
              <input
                data-testid={`agent-toggle-${agent.agent_id}`}
                type="checkbox"
                checked={checked}
                onChange={(event) =>
                  onFormChange((current) => ({
                    ...current,
                    selectedAgents: event.target.checked
                      ? [...current.selectedAgents, agent.agent_id]
                      : current.selectedAgents.filter((id) => id !== agent.agent_id),
                  }))
                }
              />
              <span>{agent.display_name}</span>
            </label>
          );
        })}
      </div>

      <div className={styles.toolbarGroup}>
        {formState.sourceType === "url" ? (
          <input
            className={styles.toolbarInput}
            data-testid="draft-url-input"
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
              data-testid="draft-file-input"
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
            {selectedFile ? <span className={styles.fileMeta}>{selectedFile.name}</span> : null}
          </div>
        ) : (
          <textarea
            className={styles.toolbarTextarea}
            data-testid="draft-text-input"
            value={formState.text}
            onChange={(event) => onFormChange((current) => ({ ...current, text: event.target.value }))}
            placeholder="Paste draft text"
          />
        )}
      </div>

      <div className={styles.toolbarGroup}>
        <button
          className={styles.button}
          data-testid="analyze-button"
          type="button"
          onClick={onSubmit}
          disabled={submitting}
        >
          {submitting ? "Submitting..." : "Analyze content"}
        </button>
        <label className={styles.ghostButton}>
          Import artifact
          <input
            key={importInputKey}
            data-testid="artifact-import-input"
            type="file"
            accept="application/json,.json"
            onChange={(event) => onImportFileChange(event.target.files?.[0] ?? null)}
            hidden
          />
        </label>
        <button
          className={styles.ghostButton}
          data-testid="export-markdown-button"
          type="button"
          onClick={() => onExport("md")}
        >
          Export Markdown
        </button>
        <button
          className={styles.ghostButton}
          data-testid="export-json-button"
          type="button"
          onClick={() => onExport("json")}
        >
          Export JSON
        </button>
        <span className={styles.statusPill} data-testid="run-status" role="status">
          {statusMessage}
        </span>
      </div>
    </section>
  );
}
