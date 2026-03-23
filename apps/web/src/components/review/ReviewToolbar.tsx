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
  previewing: boolean;
  canAnalyze: boolean;
  canPreviewUrl: boolean;
  canStopRun: boolean;
  canExport: boolean;
  canGenerateRevision: boolean;
  showGenerateRevision: boolean;
  generatingRevision: boolean;
  showNewAnalysis: boolean;
  analyzeButtonLabel: string;
  disabledAgentIds: string[];
  importInputKey: number;
  showUrlImportGuidance: boolean;
  hasLoadedContent: boolean;
  onFormChange: (updater: (current: ReviewFormState) => ReviewFormState) => void;
  onFileChange: (file: File | null) => void;
  onImportFileChange: (file: File | null) => void;
  onPreviewUrl: () => void;
  onSubmit: () => void;
  onGenerateRevision: () => void;
  onStopRun: () => void;
  onStartNewAnalysis: () => void;
  onExport: (format: "md" | "json" | "todo") => void;
}

export function ReviewToolbar({
  formState,
  agents,
  fileInputKey,
  selectedFile,
  statusMessage,
  submitting,
  previewing,
  canAnalyze,
  canPreviewUrl,
  canStopRun,
  canExport,
  canGenerateRevision,
  showGenerateRevision,
  generatingRevision,
  showNewAnalysis,
  analyzeButtonLabel,
  disabledAgentIds,
  importInputKey,
  showUrlImportGuidance,
  hasLoadedContent,
  onFormChange,
  onFileChange,
  onImportFileChange,
  onPreviewUrl,
  onSubmit,
  onGenerateRevision,
  onStopRun,
  onStartNewAnalysis,
  onExport,
}: ReviewToolbarProps) {
  return (
    <section className={styles.toolbar}>
      <div className={styles.toolbarSettings}>
        {!hasLoadedContent ? (
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
        ) : null}
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
          <option value="workspace">Workspace mode (recommended)</option>
          <option value="session">Session mode (local only)</option>
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
                disabled={disabledAgentIds.includes(agent.agent_id)}
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

      {!hasLoadedContent ? (
        <div className={styles.sourceComposer}>
          {formState.sourceType === "url" ? (
            <>
              <div className={styles.urlInputStack}>
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
                {showUrlImportGuidance ? (
                  <p className={styles.importGuidance} data-testid="url-import-guidance">
                    Import is not perfect. There might be sections from the site that don&apos;t belong to the post, that can be removed.
                  </p>
                ) : null}
              </div>
              <button
                className={styles.ghostButton}
                data-testid="import-url-button"
                type="button"
                onClick={onPreviewUrl}
                disabled={!canPreviewUrl || previewing}
              >
                {previewing ? "Importing..." : "Import draft from URL"}
              </button>
            </>
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
          ) : formState.sourceType === "text" ? (
            <textarea
              className={styles.toolbarTextarea}
              data-testid="draft-text-input"
              value={formState.text}
              onChange={(event) => onFormChange((current) => ({ ...current, text: event.target.value }))}
              placeholder="Paste draft text"
            />
          ) : null}
        </div>
      ) : null}

      <div className={styles.toolbarActions}>
        {showNewAnalysis ? (
          <button
            className={styles.button}
            data-testid="new-analysis-button"
            type="button"
            onClick={onStartNewAnalysis}
          >
            New analysis
          </button>
        ) : null}
        <button
          className={styles.button}
          data-testid="analyze-button"
          type="button"
          onClick={onSubmit}
          disabled={submitting || !canAnalyze}
        >
          {submitting ? "Submitting..." : analyzeButtonLabel}
        </button>
        <button
          className={styles.ghostButton}
          data-testid="stop-run-button"
          type="button"
          onClick={onStopRun}
          disabled={!canStopRun}
        >
          Stop run
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
          data-testid="export-todo-button"
          type="button"
          onClick={() => onExport("todo")}
          disabled={!canExport}
        >
          Export Todo
        </button>
        <button
          className={styles.ghostButton}
          data-testid="export-markdown-button"
          type="button"
          onClick={() => onExport("md")}
          disabled={!canExport}
        >
          Export Markdown
        </button>
        <button
          className={styles.ghostButton}
          data-testid="export-json-button"
          type="button"
          onClick={() => onExport("json")}
          disabled={!canExport}
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
