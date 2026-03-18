"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { AgentUsageSummary } from "@/components/review/AgentUsageSummary";
import { CommentRail } from "@/components/review/CommentRail";
import { DocumentPane } from "@/components/review/DocumentPane";
import { ReviewHero } from "@/components/review/ReviewHero";
import { ReviewSummaryPanel } from "@/components/review/ReviewSummaryPanel";
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
  API_BASE_URL,
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
  version: 2;
  artifactId: string | null;
  artifactPersistenceMode: ReviewFormState["persistenceMode"] | null;
  artifactStatus: RunStatus | null;
  artifactTitle: string | null;
  previewDocument: ArtifactDocument | null;
  hiddenPreviewBlockIds?: string[];
  formState: ReviewFormState;
  hasDownloadedJson: boolean;
}

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
    hiddenPreviewBlockIds,
    hoveredAnchorId,
    selectionDraft,
    commentDraft,
    replyDrafts,
    activeReplyComposerId,
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
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

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
    const parsedState = parseStoredWorkbenchState(stored);
    if (parsedState === null) {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      return;
    }
    const parsed = parsedState;
    let cancelled = false;

    async function restoreStoredState() {
      if (parsed.artifactId !== null) {
        try {
          const restoredArtifact = await fetchArtifact(parsed.artifactId);
          if (cancelled) {
            return;
          }
          dispatch({
            type: "RESTORE_STORED_STATE",
            artifact: restoredArtifact,
            previewDocument: null,
            formState: hydrateFormStateFromArtifact(parsed.formState, restoredArtifact),
            hasDownloadedJson: parsed.hasDownloadedJson,
            activeArtifactId: activeArtifactIdFor(restoredArtifact),
            statusMessage: `Restored ${restoredArtifact.status} ${parsed.artifactPersistenceMode ?? restoredArtifact.run_config.persistence_mode} run from the backend.`,
          });
          return;
        } catch {
          if (cancelled) {
            return;
          }
          dispatch({
            type: "RESTORE_STORED_STATE",
            artifact: null,
            previewDocument: parsed.previewDocument,
            formState: parsed.formState,
            hasDownloadedJson: parsed.hasDownloadedJson,
            activeArtifactId: null,
            statusMessage:
              parsed.artifactPersistenceMode === "workspace"
                ? "Previous workspace run is no longer available from the backend. Restored the draft only."
                : "Previous session run is no longer available from the backend. Restored the draft only.",
          });
          return;
        }
      }

      if (parsed.previewDocument !== null) {
        dispatch({
          type: "RESTORE_STORED_STATE",
          artifact: null,
          previewDocument: parsed.previewDocument,
          formState: parsed.formState,
          hasDownloadedJson: parsed.hasDownloadedJson,
          activeArtifactId: null,
          statusMessage: `Restored imported draft preview for ${parsed.previewDocument.title}.`,
        });
      }
    }

    void restoreStoredState();
    return () => {
      cancelled = true;
    };
  }, [initialArtifact]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const storedState: StoredWorkbenchState = {
      version: 2,
      artifactId: artifact?.artifact_id ?? null,
      artifactPersistenceMode: artifact?.run_config.persistence_mode ?? null,
      artifactStatus: artifact?.status ?? null,
      artifactTitle: artifact?.document?.title ?? artifact?.source.title ?? null,
      previewDocument: artifact === null ? previewDocument : null,
      hiddenPreviewBlockIds: artifact === null ? hiddenPreviewBlockIds : [],
      formState,
      hasDownloadedJson,
    };
    if (
      storedState.artifactId === null &&
      storedState.previewDocument === null &&
      !hasFormDraft(formState)
    ) {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      return;
    }
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(storedState));
  }, [artifact, previewDocument, hiddenPreviewBlockIds, formState, hasDownloadedJson]);

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

    const signal = abortControllerRef.current?.signal;
    const onAbort = () => eventSource.close();
    signal?.addEventListener("abort", onAbort);

    return () => {
      signal?.removeEventListener("abort", onAbort);
      eventSource.close();
    };
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
    (artifact?.agent_results ?? []).forEach((result) => {
      result.findings.forEach((finding) => {
        finding.anchor_ids.forEach((anchorId) => {
          const existing = map.get(anchorId);
          const color = categoryColors[finding.category] ?? "var(--ink)";
          if (existing) {
            if (!existing.colors.includes(color)) {
              existing.colors.push(color);
            }
            return;
          }
          map.set(anchorId, { colors: [color] });
        });
      });
    });
    return map;
  }, [artifact?.agent_results, normalizedThreads]);

  const claimEvidenceByBlock = useMemo(() => {
    const map = new Map<string, Array<{
      anchorId: string;
      claimText: string;
      verdict: string;
      evidenceSummary: string;
      sourceLinks: string[];
    }>>();
    const anchorsById = new Map((artifact?.anchors ?? []).map((anchor) => [anchor.id, anchor]));
    const factCheckResult = artifact?.agent_results.find((result) => result.agent_id === "fact_check");
    factCheckResult?.findings.forEach((finding) => {
      finding.anchor_ids.forEach((anchorId) => {
        const anchor = anchorsById.get(anchorId);
        const primarySegment = anchor ? anchorPrimarySegment(anchor) : null;
        if (!primarySegment) {
          return;
        }
        const items = map.get(primarySegment.block_id) ?? [];
        const sourceLinks = Array.isArray(finding.metadata.source_links)
          ? finding.metadata.source_links.map((item) => String(item))
          : (finding.sources ?? []);
        items.push({
          anchorId,
          claimText: String(finding.metadata.claim_text ?? finding.metadata.anchor_excerpt ?? finding.rationale),
          verdict: String(finding.metadata.verdict ?? "UNVERIFIABLE"),
          evidenceSummary: String(finding.metadata.evidence_summary ?? finding.rationale),
          sourceLinks,
        });
        map.set(primarySegment.block_id, items);
      });
    });
    return map;
  }, [artifact?.agent_results, artifact?.anchors]);

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
  const visiblePreviewBlockIds = useMemo(
    () => new Set((previewDocument?.blocks ?? []).filter((block) => !hiddenPreviewBlockIds.includes(block.id)).map((block) => block.id)),
    [hiddenPreviewBlockIds, previewDocument?.blocks],
  );
  const canAnalyzePreviewDocument = previewDocument !== null && visiblePreviewBlockIds.size > 0;
  const canStopRun = artifact !== null && (artifact.status === "queued" || artifact.status === "running");
  const canExport = artifact !== null;
  const showNewAnalysis = artifact !== null;
  const canPreviewUrl = formState.sourceType === "url" && formState.url.trim().length > 0;
  const canAnalyze =
    !isSubmitting &&
    ((formState.sourceType === "url" && canAnalyzePreviewDocument) ||
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

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    const { signal } = abortControllerRef.current;

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
      if (formState.sourceType === "url" && !canAnalyzePreviewDocument) {
        dispatch({ type: "SET_STATUS_MESSAGE", message: "Restore at least one imported block before starting analysis." });
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
                text: buildPreviewSubmissionText(previewDocument, hiddenPreviewBlockIds),
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

      const createdArtifact = await createRun(payload, signal);
      dispatch({ type: "SET_ARTIFACT", artifact: createdArtifact });
      dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: createdArtifact.artifact_id });
      dispatch({ type: "SET_SELECTION_DRAFT", draft: null });
      dispatch({ type: "SET_COMMENT_DRAFT", draft: "" });
      dispatch({ type: "SET_EDITING_COMMENT", commentId: null, body: "" });
      dispatch({ type: "SET_HAS_DOWNLOADED_JSON", value: false });
      dispatch({ type: "SET_STATUS_MESSAGE", message: `Artifact ${createdArtifact.artifact_id} queued` });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }
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

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    const { signal } = abortControllerRef.current;

    dispatch({ type: "SET_IS_PREVIEWING", value: true });
    dispatch({ type: "SET_STATUS_MESSAGE", message: "Importing draft from URL..." });
    try {
      const document = await previewSource({
        sourceType: "url",
        sourceLabel: formState.url,
        title: formState.title,
        url: formState.url,
      }, signal);
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
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }
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
      dispatch({ type: "SET_ACTIVE_REPLY_COMPOSER", commentId: null });
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
          canExport={canExport}
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

        <AgentUsageSummary
          agentResults={artifact?.agent_results ?? []}
          agentPlan={artifact?.agent_plan ?? []}
        />

        <section className={styles.workspace} ref={workspaceRef}>
          <ReviewSummaryPanel reviewSummary={artifact?.review_summary ?? null} />
          <DocumentPane
            document={displayDocument}
            anchors={artifact?.anchors ?? []}
            threads={normalizedThreads}
            anchorThreadMap={anchorThreadMap}
            claimEvidenceByBlock={claimEvidenceByBlock}
            selectionEnabled={artifact !== null}
            hoveredAnchorId={hoveredAnchorId}
            hiddenBlockIds={artifact === null && formState.sourceType === "url" ? hiddenPreviewBlockIds : []}
            previewPruningEnabled={artifact === null && formState.sourceType === "url" && previewDocument !== null}
            anchorRefs={anchorRefs}
            commentRefs={commentRefs}
            onHoverAnchor={(anchorId) => dispatch({ type: "SET_HOVERED_ANCHOR_ID", anchorId })}
            onSelectionDraft={(draft) => dispatch({ type: "SET_SELECTION_DRAFT", draft: artifact !== null ? draft : null })}
            onHideBlock={(blockId) => dispatch({ type: "HIDE_PREVIEW_BLOCK", blockId })}
            onRestoreBlock={(blockId) => dispatch({ type: "RESTORE_PREVIEW_BLOCK", blockId })}
            onRestoreAllBlocks={() => dispatch({ type: "RESTORE_ALL_PREVIEW_BLOCKS" })}
            replyDrafts={replyDrafts}
            editingCommentId={editingCommentId}
            editingBody={editingBody}
            onReplyDraftChange={(commentId, value) => {
              dispatch({ type: "SET_REPLY_DRAFT", commentId, body: value });
            }}
            activeReplyComposerId={activeReplyComposerId}
            onToggleReplyComposer={(commentId) =>
              dispatch({
                type: "SET_ACTIVE_REPLY_COMPOSER",
                commentId: activeReplyComposerId === commentId ? null : commentId,
              })
            }
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
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<StoredWorkbenchState>;
  return (
    candidate.version === 2
    && typeof candidate.formState === "object"
    && candidate.formState !== null
    && typeof candidate.hasDownloadedJson === "boolean"
    && (!("hiddenPreviewBlockIds" in candidate)
      || candidate.hiddenPreviewBlockIds === undefined
      || (Array.isArray(candidate.hiddenPreviewBlockIds) && candidate.hiddenPreviewBlockIds.every((item) => typeof item === "string")))
    && ("artifactId" in candidate)
    && ("previewDocument" in candidate)
  );
}

function isAnalysisArtifact(value: unknown): value is AnalysisArtifact {
  return typeof value === "object" && value !== null && "artifact_id" in value && "status" in value;
}

function parseStoredWorkbenchState(raw: string): StoredWorkbenchState | null {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (isStoredWorkbenchState(parsed) && isReviewFormState(parsed.formState)) {
      return parsed;
    }
    if (isAnalysisArtifact(parsed)) {
      return {
        version: 2,
        artifactId: parsed.artifact_id,
        artifactPersistenceMode: parsed.run_config.persistence_mode,
        artifactStatus: parsed.status,
        artifactTitle: parsed.document?.title ?? parsed.source.title ?? null,
        previewDocument: null,
        formState: hydrateFormStateFromArtifact(initialWorkbenchState.formState, parsed),
        hasDownloadedJson: false,
      };
    }
  } catch {
    return null;
  }
  return null;
}

function isReviewFormState(value: unknown): value is ReviewFormState {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<ReviewFormState>;
  return (
    (candidate.sourceType === "text" || candidate.sourceType === "url" || candidate.sourceType === "file")
    && typeof candidate.title === "string"
    && typeof candidate.sourceLabel === "string"
    && typeof candidate.text === "string"
    && typeof candidate.url === "string"
    && (candidate.persistenceMode === "session" || candidate.persistenceMode === "workspace")
    && typeof candidate.includeDebugTrace === "boolean"
    && Array.isArray(candidate.selectedAgents)
    && candidate.selectedAgents.every((item) => typeof item === "string")
  );
}

function hydrateFormStateFromArtifact(current: ReviewFormState, artifact: AnalysisArtifact): ReviewFormState {
  return {
    ...current,
    title: artifact.document?.title ?? artifact.source.title ?? current.title,
    text: artifact.document?.raw_content ?? artifact.document?.text ?? current.text,
    url: artifact.source.url ?? current.url,
    sourceLabel: artifact.source.source_label,
    selectedAgents: artifact.run_config.selected_agents,
    persistenceMode: artifact.run_config.persistence_mode,
    includeDebugTrace: artifact.run_config.include_debug_trace,
  };
}

function buildPreviewSubmissionText(document: ArtifactDocument, hiddenBlockIds: string[]): string {
  const hiddenIds = new Set(hiddenBlockIds);
  return document.blocks
    .filter((block) => !hiddenIds.has(block.id))
    .map((block) => block.markdown?.trim() || block.text.trim())
    .filter((block) => block.length > 0)
    .join("\n\n");
}

function activeArtifactIdFor(artifact: AnalysisArtifact): string | null {
  return artifact.status === "running" || artifact.status === "queued" ? artifact.artifact_id : null;
}

function hasFormDraft(formState: ReviewFormState): boolean {
  return Boolean(
    formState.title
      || formState.text
      || formState.url
      || (formState.sourceType !== "text")
      || formState.sourceLabel !== initialWorkbenchState.formState.sourceLabel,
  );
}
