"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { CommentRail } from "@/components/review/CommentRail";
import { DocumentPane } from "@/components/review/DocumentPane";
import { ReviewHero } from "@/components/review/ReviewHero";
import { ReviewToolbar, type ReviewFormState } from "@/components/review/ReviewToolbar";
import { RunMetrics } from "@/components/review/RunMetrics";
import { SelectionBanner } from "@/components/review/SelectionBanner";
import { categoryColors } from "@/components/review/category-colors";
import {
  initialWorkbenchState,
  workbenchReducer,
  type WorkbenchAction,
} from "@/components/review/workbench-state";
import {
  addReply,
  cancelRun,
  createComment,
  createRun,
  deleteHumanComment,
  deleteReply,
  fetchAgents,
  fetchArtifact,
  getExportUrl,
  importArtifact,
  previewSource,
  updateHumanComment,
  updateReviewState,
} from "@/lib/api";
import type {
  AgentCatalogEntry,
  AnalysisArtifact,
  ArtifactDocument,
  ArtifactThread,
  ReviewState,
  RunStatus,
} from "@/lib/types";
import { anchorPrimarySegment } from "@/lib/types";

interface ReviewWorkbenchProps {
  initialArtifact: AnalysisArtifact | null;
}

interface StoredWorkbenchState {
  artifact: AnalysisArtifact | null;
  previewDocument: ArtifactDocument | null;
  formState: ReviewFormState;
  hasDownloadedJson: boolean;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const SESSION_STORAGE_KEY = "content-evaluation:artifact";
const TERMINAL_RUN_STATUSES = new Set<RunStatus>(["completed", "failed", "canceled"]);

export function ReviewWorkbench({ initialArtifact }: ReviewWorkbenchProps) {
  const [state, dispatch] = useReducer(workbenchReducer, {
    ...initialWorkbenchState,
    artifact: initialArtifact,
    activeArtifactId: initialArtifact?.artifact_id ?? null,
  });

  const {
    artifact,
    previewDocument,
    agents,
    statusMessage,
    hoveredAnchorId,
    selectionDraft,
    commentDraft,
    replyDrafts,
    editingCommentId,
    editingBody,
    isSubmitting,
    isPreviewing,
    selectedFile,
    fileInputKey,
    importInputKey,
    activeArtifactId,
    hasDownloadedJson,
    formState,
  } = state;

  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const anchorRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const commentRefs = useRef<Record<string, HTMLElement | null>>({});
  const refreshInFlightRef = useRef<Promise<AnalysisArtifact> | null>(null);
  const queuedRefreshArtifactIdRef = useRef<string | null>(null);

  useEffect(() => {
    fetchAgents()
      .then((catalog) => {
        dispatch({ type: "SET_AGENTS", agents: catalog });
        dispatch({
          type: "UPDATE_FORM_STATE",
          updater: (current) => {
            if (current.selectedAgents.length > 0) {
              return current;
            }
            return {
              ...current,
              selectedAgents: catalog.filter((agent) => agent.default_enabled).map((agent) => agent.agent_id),
            };
          },
        });
      })
      .catch(() => {
        dispatch({ type: "SET_STATUS_MESSAGE", message: "Could not load the agent catalog." });
      });
  }, []);

  useEffect(() => {
    if (initialArtifact !== null || typeof window === "undefined") {
      return;
    }
    const stored = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!stored) {
      return;
    }
    try {
      const parsed = JSON.parse(stored) as StoredWorkbenchState | AnalysisArtifact;
      if (isStoredWorkbenchState(parsed)) {
        let activeId: string | null = null;
        let message = state.statusMessage;
        if (parsed.artifact !== null) {
          activeId =
            parsed.artifact.status === "running" || parsed.artifact.status === "queued"
              ? parsed.artifact.artifact_id
              : null;
          message = `Restored ${parsed.artifact.status} artifact from this browser session.`;
        } else if (parsed.previewDocument !== null) {
          message = `Restored imported draft preview for ${parsed.previewDocument.title}.`;
        }
        dispatch({
          type: "RESTORE_STORED_STATE",
          artifact: parsed.artifact,
          previewDocument: parsed.previewDocument,
          formState: parsed.formState,
          hasDownloadedJson: parsed.hasDownloadedJson,
          activeArtifactId: activeId,
          statusMessage: message,
        });
        return;
      }
      if (isAnalysisArtifact(parsed)) {
        dispatch({ type: "SET_ARTIFACT", artifact: parsed });
        dispatch({
          type: "SET_ACTIVE_ARTIFACT_ID",
          id: parsed.status === "running" || parsed.status === "queued" ? parsed.artifact_id : null,
        });
        dispatch({ type: "SET_STATUS_MESSAGE", message: `Restored ${parsed.status} artifact from this browser session.` });
        dispatch({
          type: "UPDATE_FORM_STATE",
          updater: (current) => ({
            ...current,
            title: parsed.document?.title ?? parsed.source.title ?? current.title,
            text: parsed.document?.raw_content ?? parsed.document?.text ?? current.text,
            url: parsed.source.url ?? current.url,
            sourceLabel: parsed.source.source_label,
            selectedAgents: parsed.run_config.selected_agents,
            persistenceMode: parsed.run_config.persistence_mode,
            includeDebugTrace: parsed.run_config.include_debug_trace,
          }),
        });
      }
    } catch {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }, [initialArtifact]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const storedState: StoredWorkbenchState = {
      artifact,
      previewDocument,
      formState,
      hasDownloadedJson,
    };
    if (
      artifact === null &&
      previewDocument === null &&
      !formState.title &&
      !formState.text &&
      !formState.url &&
      formState.sourceType === "text"
    ) {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      return;
    }
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(storedState));
  }, [artifact, previewDocument, formState, hasDownloadedJson]);

  const refreshArtifact = useCallback(async (artifactId: string) => {
    const updated = await fetchArtifact(artifactId);
    dispatch({ type: "SET_ARTIFACT", artifact: updated });
    if (updated.document !== null) {
      dispatch({ type: "SET_PREVIEW_DOCUMENT", document: null });
    }
    dispatch({ type: "SET_STATUS_MESSAGE", message: `Run ${updated.status}` });
    return updated;
  }, []);

  const refreshArtifactCoalesced = useCallback(
    async (artifactId: string): Promise<AnalysisArtifact> => {
      if (refreshInFlightRef.current !== null) {
        queuedRefreshArtifactIdRef.current = artifactId;
        return refreshInFlightRef.current;
      }

      const request = refreshArtifact(artifactId).finally(() => {
        refreshInFlightRef.current = null;
        const queuedArtifactId = queuedRefreshArtifactIdRef.current;
        queuedRefreshArtifactIdRef.current = null;
        if (queuedArtifactId !== null) {
          void refreshArtifactCoalesced(queuedArtifactId);
        }
      });
      refreshInFlightRef.current = request;
      return request;
    },
    [refreshArtifact],
  );

  useEffect(() => {
    if (!activeArtifactId) {
      return;
    }

    const eventSource = new EventSource(`${API_BASE_URL}/api/v1/runs/${activeArtifactId}/events`);
    eventSource.onmessage = async (event) => {
      const parsed = JSON.parse(event.data) as { snapshot_available?: boolean };
      if (parsed.snapshot_available) {
        const updated = await refreshArtifactCoalesced(activeArtifactId);
        if (TERMINAL_RUN_STATUSES.has(updated.status)) {
          dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: null });
          eventSource.close();
        }
      }
    };
    eventSource.onerror = () => {
      dispatch({ type: "SET_STATUS_MESSAGE", message: "Live artifact updates disconnected. Refreshing on the next action." });
      eventSource.close();
    };
    return () => eventSource.close();
  }, [activeArtifactId, refreshArtifactCoalesced]);

  const normalizedThreads = useMemo(() => {
    if (artifact === null || artifact.document === null) {
      return [] as ArtifactThread[];
    }

    const blockIndexById = new Map(artifact.document.blocks.map((block) => [block.id, block.index]));
    return [...artifact.threads]
      .map((thread) => ({
        ...thread,
        comments: [...thread.comments].sort((left, right) => {
          const createdAtDifference = new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
          if (createdAtDifference !== 0) {
            return createdAtDifference;
          }
          return left.id.localeCompare(right.id);
        }),
      }))
      .sort((left, right) => {
        const leftPrimarySegment = anchorPrimarySegment(left.anchor);
        const rightPrimarySegment = anchorPrimarySegment(right.anchor);
        const leftBlockIndex = blockIndexById.get(leftPrimarySegment.block_id) ?? Number.MAX_SAFE_INTEGER;
        const rightBlockIndex = blockIndexById.get(rightPrimarySegment.block_id) ?? Number.MAX_SAFE_INTEGER;
        if (leftBlockIndex !== rightBlockIndex) {
          return leftBlockIndex - rightBlockIndex;
        }
        if (leftPrimarySegment.start_offset !== rightPrimarySegment.start_offset) {
          return leftPrimarySegment.start_offset - rightPrimarySegment.start_offset;
        }
        if (leftPrimarySegment.end_offset !== rightPrimarySegment.end_offset) {
          return leftPrimarySegment.end_offset - rightPrimarySegment.end_offset;
        }
        return left.anchor.id.localeCompare(right.anchor.id);
      });
  }, [artifact]);

  const anchorThreadMap = useMemo(() => {
    const map = new Map<string, { colors: string[] }>();
    normalizedThreads.forEach((thread) => {
      map.set(thread.anchor.id, {
        colors: thread.comments.map((comment) => categoryColors[comment.category] ?? "var(--ink)"),
      });
    });
    return map;
  }, [normalizedThreads]);

  const progress = useMemo(() => {
    if (artifact === null) {
      return 0;
    }
    const latestProgress = [...artifact.events].reverse().find((event) => typeof event.progress === "number");
    if (latestProgress?.progress !== undefined && latestProgress.progress !== null) {
      return latestProgress.progress;
    }
    if (!artifact.agent_plan.length) {
      return artifact.status === "completed" ? 1 : 0;
    }
    const completed = artifact.agent_plan.filter((item) => item.status === "completed").length;
    return completed / artifact.agent_plan.length;
  }, [artifact]);

  const displayDocument = artifact?.document ?? previewDocument;
  const canStopRun = artifact !== null && (artifact.status === "queued" || artifact.status === "running");
  const showNewAnalysis = artifact !== null;
  const canPreviewUrl = formState.sourceType === "url" && formState.url.trim().length > 0;
  const canAnalyze =
    !isSubmitting &&
    ((formState.sourceType === "url" && previewDocument !== null) ||
      (formState.sourceType === "text" && formState.text.trim().length > 0) ||
      (formState.sourceType === "file" && selectedFile !== null));
  const latestResumeEvent = useMemo(
    () =>
      [...(artifact?.events ?? [])]
        .reverse()
        .find((event) => event.event_type === "run" && event.status === "resumed"),
    [artifact?.events],
  );
  const isProgressActive = artifact !== null && (artifact.status === "queued" || artifact.status === "running");

  async function maybeReplaceCurrentAnalysis(resetForm: boolean) {
    const hasCurrentAnalysis = artifact !== null || previewDocument !== null;
    if (!hasCurrentAnalysis) {
      if (resetForm) {
        dispatch({ type: "CLEAR_ANALYSIS_STATE", resetForm: true, currentAgents: agents });
      }
      return true;
    }

    if (!hasDownloadedJson && typeof window !== "undefined") {
      const confirmed = window.confirm(
        "Start a new analysis? The current analysis has not been downloaded as JSON and will be lost.",
      );
      if (!confirmed) {
        return false;
      }
    }

    if (artifact !== null && (artifact.status === "queued" || artifact.status === "running")) {
      try {
        await cancelRun(artifact.artifact_id);
      } catch {
        dispatch({ type: "SET_STATUS_MESSAGE", message: "Could not stop the current run before starting over." });
        return false;
      }
    }

    dispatch({ type: "CLEAR_ANALYSIS_STATE", resetForm, currentAgents: agents });
    return true;
  }

  async function handleSubmit() {
    const isUrlPreviewRun = formState.sourceType === "url" && previewDocument !== null && artifact === null;
    if (!isUrlPreviewRun && (artifact !== null || previewDocument !== null)) {
      const replaced = await maybeReplaceCurrentAnalysis(false);
      if (!replaced) {
        return;
      }
    }

    dispatch({ type: "SET_STATUS_MESSAGE", message: "Submitting analysis session..." });
    dispatch({ type: "SET_IS_SUBMITTING", value: true });
    try {
      if (formState.sourceType === "file") {
        if (selectedFile === null) {
          dispatch({ type: "SET_STATUS_MESSAGE", message: "Choose a .txt or .md file first." });
          return;
        }
        if (!/\.(txt|md)$/i.test(selectedFile.name)) {
          dispatch({ type: "SET_STATUS_MESSAGE", message: "Only .txt and .md uploads are supported." });
          return;
        }
      }

      if (formState.sourceType === "text" && !formState.text.trim()) {
        dispatch({ type: "SET_STATUS_MESSAGE", message: "Paste draft text before starting analysis." });
        return;
      }

      if (formState.sourceType === "url" && previewDocument === null) {
        dispatch({ type: "SET_STATUS_MESSAGE", message: "Import the draft from the URL before starting analysis." });
        return;
      }

      const payload =
        formState.sourceType === "file" && selectedFile !== null
          ? {
              sourceType: "file" as const,
              sourceLabel: selectedFile.name,
              title: formState.title || selectedFile.name,
              text: await selectedFile.text(),
              selectedAgents: resolveSelectedAgents(formState.selectedAgents, agents),
              persistenceMode: formState.persistenceMode,
              includeDebugTrace: formState.includeDebugTrace,
            }
          : formState.sourceType === "url" && previewDocument !== null
            ? {
                sourceType: "url" as const,
                sourceLabel: formState.url,
                title: formState.title || previewDocument.title,
                text: previewDocument.raw_content || previewDocument.text,
                url: formState.url,
                selectedAgents: resolveSelectedAgents(formState.selectedAgents, agents),
                persistenceMode: formState.persistenceMode,
                includeDebugTrace: formState.includeDebugTrace,
              }
            : {
                sourceType: "text" as const,
                sourceLabel: formState.sourceLabel || "Manual input",
                title: formState.title,
                text: formState.text,
                selectedAgents: resolveSelectedAgents(formState.selectedAgents, agents),
                persistenceMode: formState.persistenceMode,
                includeDebugTrace: formState.includeDebugTrace,
              };

      const createdArtifact = await createRun(payload);
      dispatch({ type: "SET_ARTIFACT", artifact: createdArtifact });
      dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: createdArtifact.artifact_id });
      dispatch({ type: "SET_SELECTION_DRAFT", draft: null });
      dispatch({ type: "SET_COMMENT_DRAFT", draft: "" });
      dispatch({ type: "SET_EDITING_COMMENT", commentId: null, body: "" });
      dispatch({ type: "SET_HAS_DOWNLOADED_JSON", value: false });
      dispatch({ type: "SET_STATUS_MESSAGE", message: `Artifact ${createdArtifact.artifact_id} queued` });
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not submit run" });
    } finally {
      dispatch({ type: "SET_IS_SUBMITTING", value: false });
    }
  }

  async function handlePreviewUrl() {
    if (!formState.url.trim()) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: "Enter a URL first." });
      return;
    }

    const replacingCurrentAnalysis = artifact !== null || previewDocument !== null;
    if (replacingCurrentAnalysis) {
      const replaced = await maybeReplaceCurrentAnalysis(false);
      if (!replaced) {
        return;
      }
    }

    dispatch({ type: "SET_IS_PREVIEWING", value: true });
    dispatch({ type: "SET_STATUS_MESSAGE", message: "Importing draft from URL..." });
    try {
      const document = await previewSource({
        sourceType: "url",
        sourceLabel: formState.url,
        title: formState.title,
        url: formState.url,
      });
      dispatch({ type: "SET_PREVIEW_DOCUMENT", document });
      dispatch({ type: "SET_HAS_DOWNLOADED_JSON", value: false });
      dispatch({ type: "SET_STATUS_MESSAGE", message: `Imported draft preview from ${formState.url}` });
      dispatch({
        type: "UPDATE_FORM_STATE",
        updater: (current) => ({
          ...current,
          title: current.title || document.title,
          sourceLabel: current.url || current.sourceLabel,
        }),
      });
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not import draft from URL" });
    } finally {
      dispatch({ type: "SET_IS_PREVIEWING", value: false });
    }
  }

  async function handleImportFile(file: File | null) {
    if (file === null) {
      return;
    }

    const replacingCurrentAnalysis = artifact !== null || previewDocument !== null;
    if (replacingCurrentAnalysis) {
      const replaced = await maybeReplaceCurrentAnalysis(false);
      if (!replaced) {
        dispatch({ type: "BUMP_IMPORT_INPUT_KEY" });
        return;
      }
    }

    try {
      const parsed = JSON.parse(await file.text()) as AnalysisArtifact;
      const imported = await importArtifact(parsed);
      dispatch({ type: "SET_ARTIFACT", artifact: imported });
      dispatch({ type: "SET_PREVIEW_DOCUMENT", document: null });
      dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: null });
      dispatch({ type: "SET_HAS_DOWNLOADED_JSON", value: true });
      dispatch({ type: "SET_STATUS_MESSAGE", message: `Imported artifact ${imported.artifact_id}` });
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not import artifact" });
    } finally {
      dispatch({ type: "BUMP_IMPORT_INPUT_KEY" });
    }
  }

  async function handleStopRun() {
    if (artifact === null || (artifact.status !== "queued" && artifact.status !== "running")) {
      return;
    }
    try {
      const canceledArtifact = await cancelRun(artifact.artifact_id);
      dispatch({ type: "SET_ARTIFACT", artifact: canceledArtifact });
      dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: null });
      dispatch({ type: "SET_STATUS_MESSAGE", message: "Run canceled" });
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not stop the run" });
    }
  }

  async function handleStartNewAnalysis() {
    const replaced = await maybeReplaceCurrentAnalysis(true);
    if (!replaced) {
      return;
    }
    dispatch({ type: "SET_STATUS_MESSAGE", message: "Started a new analysis draft." });
  }

  async function handleCreateComment() {
    if (artifact === null || selectionDraft === null || !commentDraft.trim()) {
      return;
    }
    try {
      await createComment({
        artifactId: artifact.artifact_id,
        body: commentDraft,
        blockId: selectionDraft.blockId,
        startOffset: selectionDraft.startOffset,
        endOffset: selectionDraft.endOffset,
        quote: selectionDraft.quote,
      });
      await refreshArtifact(artifact.artifact_id);
      dispatch({ type: "SET_SELECTION_DRAFT", draft: null });
      dispatch({ type: "SET_COMMENT_DRAFT", draft: "" });
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not save comment." });
    }
  }

  async function handleReply(commentId: string) {
    if (artifact === null) {
      return;
    }
    const body = replyDrafts[commentId]?.trim();
    if (!body) {
      return;
    }
    try {
      await addReply(commentId, body);
      await refreshArtifact(artifact.artifact_id);
      dispatch({ type: "SET_REPLY_DRAFT", commentId, body: "" });
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not save reply." });
    }
  }

  async function handleDeleteReply(replyId: string) {
    if (artifact === null) {
      return;
    }
    try {
      await deleteReply(replyId);
      await refreshArtifact(artifact.artifact_id);
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not delete reply." });
    }
  }

  async function handleReviewState(commentId: string, reviewState: ReviewState) {
    if (artifact === null) {
      return;
    }
    try {
      const currentState =
        artifact.threads.flatMap((thread) => thread.comments).find((comment) => comment.id === commentId)?.review_state
        ?? "unreviewed";
      const nextState: ReviewState = currentState === reviewState ? "unreviewed" : reviewState;
      await updateReviewState(commentId, nextState);
      await refreshArtifact(artifact.artifact_id);
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not update review state." });
    }
  }

  async function handleSaveEdit(commentId: string) {
    if (artifact === null || !editingBody.trim()) {
      return;
    }
    try {
      await updateHumanComment(commentId, editingBody);
      await refreshArtifact(artifact.artifact_id);
      dispatch({ type: "SET_EDITING_COMMENT", commentId: null, body: "" });
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not save edit." });
    }
  }

  async function handleDeleteHumanComment(commentId: string) {
    if (artifact === null) {
      return;
    }
    try {
      await deleteHumanComment(commentId);
      await refreshArtifact(artifact.artifact_id);
      if (editingCommentId === commentId) {
        dispatch({ type: "SET_EDITING_COMMENT", commentId: null, body: "" });
      }
    } catch (error) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: error instanceof Error ? error.message : "Could not delete comment." });
    }
  }

  function handleExport(format: "md" | "json" | "todo") {
    if (artifact === null) {
      return;
    }
    if (format === "json") {
      dispatch({ type: "SET_HAS_DOWNLOADED_JSON", value: true });
    }
    window.open(getExportUrl(artifact.artifact_id, format), "_blank", "noopener,noreferrer");
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <ReviewHero
          overallScore={artifact?.summary?.overall_score ?? 0}
          verdict={artifact?.summary?.verdict ?? (displayDocument ? "Imported draft ready for review" : "No artifact loaded")}
        />

        <ReviewToolbar
          formState={formState}
          agents={agents}
          fileInputKey={fileInputKey}
          selectedFile={selectedFile}
          statusMessage={statusMessage}
          submitting={isSubmitting}
          previewing={isPreviewing}
          canAnalyze={canAnalyze}
          canPreviewUrl={canPreviewUrl}
          canStopRun={canStopRun}
          showNewAnalysis={showNewAnalysis}
          importInputKey={importInputKey}
          onFormChange={(updater) =>
            dispatch({
              type: "UPDATE_FORM_STATE",
              updater: (current) => {
                const next = updater(current);
                if (next.selectedAgents !== current.selectedAgents) {
                  return {
                    ...next,
                    selectedAgents: resolveSelectedAgents(next.selectedAgents, agents),
                  };
                }
                return next;
              },
            })
          }
          onFileChange={(file) => {
            dispatch({ type: "SET_SELECTED_FILE", file });
            dispatch({ type: "BUMP_FILE_INPUT_KEY" });
            dispatch({
              type: "UPDATE_FORM_STATE",
              updater: (current) => ({
                ...current,
                sourceLabel: file?.name ?? "upload",
                title: file?.name ?? current.title,
              }),
            });
          }}
          onImportFileChange={handleImportFile}
          onPreviewUrl={handlePreviewUrl}
          onSubmit={handleSubmit}
          onStopRun={handleStopRun}
          onStartNewAnalysis={handleStartNewAnalysis}
          onExport={handleExport}
        />

        {artifact?.error_message ? <section className={styles.errorBanner}>{artifact.error_message}</section> : null}

        <SelectionBanner
          selectionDraft={selectionDraft}
          commentDraft={commentDraft}
          onCommentDraftChange={(value) => dispatch({ type: "SET_COMMENT_DRAFT", draft: value })}
          onSave={handleCreateComment}
          onCancel={() => dispatch({ type: "SET_SELECTION_DRAFT", draft: null })}
        />

        <section className={styles.progressPanel}>
          <div className={styles.sectionTitle}>Run progress</div>
          <div
            className={`${styles.progressTrack} ${isProgressActive ? styles.progressTrackActive : ""}`}
            data-testid="progress-track"
            aria-hidden="true"
          >
            <div
              className={`${styles.progressFill} ${isProgressActive ? styles.progressFillActive : ""}`}
              data-testid="progress-fill"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
          <div className={styles.progressMeta}>
            <span>{Math.round(progress * 100)}% complete</span>
            <span>{artifact?.status ?? (previewDocument ? "draft imported" : "idle")}</span>
          </div>
          {latestResumeEvent ? (
            <div className={styles.progressNote} data-testid="run-resumed-note">
              {latestResumeEvent.message}
              {latestResumeEvent.attempt ? ` (${latestResumeEvent.attempt}${latestResumeEvent.max_attempts ? ` of ${latestResumeEvent.max_attempts}` : ""})` : ""}
            </div>
          ) : null}
          <div className={styles.agentStatusGrid}>
            {(artifact?.agent_plan ?? []).map((item) => (
              <article key={item.agent_id} className={styles.agentStatusCard} data-testid={`agent-plan-${item.agent_id}`}>
                <strong>{item.display_name}</strong>
                <span className={styles.pill}>{item.status}</span>
                <p className={styles.agentStatusCopy}>{item.message ?? item.category}</p>
              </article>
            ))}
          </div>
        </section>

        <CommentRail events={artifact?.events ?? []} />

        <RunMetrics summary={artifact?.summary ?? null} />

        <section className={styles.workspace} ref={workspaceRef}>
          <DocumentPane
            document={displayDocument}
            anchors={artifact?.anchors ?? []}
            threads={normalizedThreads}
            anchorThreadMap={anchorThreadMap}
            selectionEnabled={artifact !== null}
            hoveredAnchorId={hoveredAnchorId}
            anchorRefs={anchorRefs}
            commentRefs={commentRefs}
            onHoverAnchor={(anchorId) => dispatch({ type: "SET_HOVERED_ANCHOR_ID", anchorId })}
            onSelectionDraft={(draft) => dispatch({ type: "SET_SELECTION_DRAFT", draft: artifact !== null ? draft : null })}
            replyDrafts={replyDrafts}
            editingCommentId={editingCommentId}
            editingBody={editingBody}
            onReplyDraftChange={(commentId, value) => {
              dispatch({ type: "SET_REPLY_DRAFT", commentId, body: value });
            }}
            onAddReply={handleReply}
            onDeleteReply={handleDeleteReply}
            onReviewState={handleReviewState}
            onStartEditing={(commentId, body) => {
              dispatch({ type: "SET_EDITING_COMMENT", commentId, body });
            }}
            onEditingBodyChange={(value) => dispatch({ type: "SET_EDITING_BODY", body: value })}
            onSaveEdit={handleSaveEdit}
            onCancelEdit={() => {
              dispatch({ type: "SET_EDITING_COMMENT", commentId: null, body: "" });
            }}
            onDeleteComment={handleDeleteHumanComment}
          />
        </section>
      </div>
    </main>
  );
}

function resolveSelectedAgents(selectedAgents: string[], agents: AgentCatalogEntry[]): string[] {
  const agentMap = new Map(agents.map((agent) => [agent.agent_id, agent]));
  const visited = new Set<string>();

  function visit(agentId: string) {
    if (visited.has(agentId)) {
      return;
    }
    visited.add(agentId);
    const agent = agentMap.get(agentId);
    agent?.depends_on.forEach(visit);
  }

  selectedAgents.forEach(visit);
  return [...visited];
}

function isStoredWorkbenchState(value: unknown): value is StoredWorkbenchState {
  return typeof value === "object" && value !== null && "formState" in value;
}

function isAnalysisArtifact(value: unknown): value is AnalysisArtifact {
  return typeof value === "object" && value !== null && "artifact_id" in value && "status" in value;
}
