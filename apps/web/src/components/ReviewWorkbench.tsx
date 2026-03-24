"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { AgentUsageSummary } from "@/components/review/AgentUsageSummary";
import { CommentRail } from "@/components/review/CommentRail";
import { DocumentPane } from "@/components/review/DocumentPane";
import { RevisedMarkdownPanel } from "@/components/review/RevisedMarkdownPanel";
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
  applyRevisedMarkdown,
  appendAgents,
  API_BASE_URL,
  cancelRun,
  createComment,
  createRun,
  deleteHumanComment,
  deleteReply,
  fetchAgents,
  fetchArtifact,
  getExportUrl,
  generateRevisedMarkdown,
  importArtifact,
  previewSource,
  queueResearch,
  updateRevisedMarkdownDiffReview,
  updateHumanComment,
  updateReviewState,
} from "@/lib/api";
import type {
  AgentCatalogEntry,
  AnalysisArtifact,
  ArtifactEvent,
  ArtifactDocument,
  ArtifactComment,
  ArtifactThread,
  ReviewState,
  RevisionMode,
  RunStatus,
} from "@/lib/types";
import { anchorPrimarySegment } from "@/lib/types";

interface ReviewWorkbenchProps {
  initialArtifact: AnalysisArtifact | null;
}

type WorkbenchPhase = "intake" | "running" | "review" | "diff_review";

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
    activeArtifactId: initialArtifact ? activeArtifactIdFor(initialArtifact) : null,
    formState: initialArtifact
      ? hydrateFormStateFromArtifact(initialWorkbenchState.formState, initialArtifact)
      : initialWorkbenchState.formState,
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
    isGeneratingRevision,
    isSavingDiffReview,
    isApplyingRevision,
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
  const historicalAnchorRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const historicalCommentRefs = useRef<Record<string, HTMLElement | null>>({});
  const refreshInFlightRef = useRef<Promise<AnalysisArtifact> | null>(null);
  const queuedRefreshArtifactIdRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [isQueuingResearch, setIsQueuingResearch] = useState(false);
  const [rewritePromptOpen, setRewritePromptOpen] = useState(false);
  const [rewriteDirectionPrompt, setRewriteDirectionPrompt] = useState("");

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (artifact?.diff_review) {
      setRewritePromptOpen(false);
    }
  }, [artifact?.diff_review]);

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
    return normalizeThreads(artifact?.document ?? null, artifact?.threads ?? []);
  }, [artifact]);

  const anchorThreadMap = useMemo(() => {
    return buildAnchorThreadMap(normalizedThreads, artifact?.agent_results ?? []);
  }, [artifact?.agent_results, normalizedThreads]);
  const currentRevisionId = artifact?.document?.revision_id ?? null;
  const inlineHistoricalThreads = useMemo(
    () => normalizedThreads.filter((thread) => isHistoricalThread(thread, currentRevisionId)),
    [currentRevisionId, normalizedThreads],
  );
  const previousDraftSnapshot = artifact?.previous_draft_snapshot ?? null;
  const inlineHistoricalCommentIds = useMemo(
    () => new Set(inlineHistoricalThreads.flatMap((thread) => thread.comments.map((comment) => comment.id))),
    [inlineHistoricalThreads],
  );
  const historicalSnapshotThreads = useMemo(() => {
    if (previousDraftSnapshot === null) {
      return [] as ArtifactThread[];
    }
    const filteredThreads = previousDraftSnapshot.threads
      .map((thread) => ({
        ...thread,
        comments: thread.comments.filter((comment) => !inlineHistoricalCommentIds.has(comment.id)),
      }))
      .filter((thread) => thread.comments.length > 0);
    return normalizeThreads(previousDraftSnapshot.document, filteredThreads);
  }, [inlineHistoricalCommentIds, previousDraftSnapshot]);
  const historicalAnchorThreadMap = useMemo(
    () => buildAnchorThreadMap(historicalSnapshotThreads, previousDraftSnapshot?.agent_results ?? []),
    [historicalSnapshotThreads, previousDraftSnapshot?.agent_results],
  );
  const hasHistoricalFindings = inlineHistoricalThreads.length > 0 || historicalSnapshotThreads.length > 0;

  const workbenchPhase = useMemo(
    () => getWorkbenchPhase(artifact),
    [artifact],
  );
  const followUpRunMode = useMemo(
    () => getFollowUpRunMode(artifact),
    [artifact],
  );
  const isIntakePhase = workbenchPhase === "intake";
  const isRunningPhase = workbenchPhase === "running";
  const isReviewPhase = workbenchPhase === "review";
  const isDiffReviewPhase = workbenchPhase === "diff_review";

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
  const diffReview = useMemo(() => getArtifactDiffReview(artifact), [artifact]);
  const revisedMarkdownApplied = useMemo(() => isRevisedMarkdownApplied(artifact), [artifact]);
  const hasAcceptedSuggestions = useMemo(() => hasAcceptedRevisionSuggestions(artifact), [artifact]);
  const revisionWorkflowPending = diffReview !== null && !revisedMarkdownApplied;
  const visiblePreviewBlockIds = useMemo(
    () => new Set((previewDocument?.blocks ?? []).filter((block) => !hiddenPreviewBlockIds.includes(block.id)).map((block) => block.id)),
    [hiddenPreviewBlockIds, previewDocument?.blocks],
  );
  const canAnalyzePreviewDocument = previewDocument !== null && visiblePreviewBlockIds.size > 0;
  const canStopRun = artifact !== null && (artifact.status === "queued" || artifact.status === "running");
  const canExport = artifact !== null;
  const isTerminalArtifact = artifact !== null && TERMINAL_RUN_STATUSES.has(artifact.status);
  const showNewAnalysis = artifact !== null && isReviewPhase;
  const isFollowUpRunInProgress = artifact !== null && isReviewPhase && canStopRun && followUpRunMode !== null;
  const followUpRunLabel = followUpRunMode === "research" ? "Targeted research running" : "Additional analysis running";
  const researchPromptSeed = useMemo(() => getSuggestedResearchPrompt(artifact), [artifact]);
  const completedAgentIds = useMemo(() => {
    if (artifact === null) {
      return new Set<string>();
    }
    const completed = new Set(
      artifact.agent_plan
        .filter((item) => item.status === "completed")
        .map((item) => item.agent_id),
    );
    artifact.agent_results
      .filter((item) => item.status === "completed")
      .forEach((item) => completed.add(item.agent_id));
    return completed;
  }, [artifact]);
  const appendableSelectedAgents = useMemo(
    () => formState.selectedAgents.filter((agentId) => !completedAgentIds.has(agentId)),
    [completedAgentIds, formState.selectedAgents],
  );
  const canPreviewUrl = formState.sourceType === "url" && formState.url.trim().length > 0;
  const showUrlImportGuidance =
    formState.sourceType === "url"
    && previewDocument !== null
    && isIntakePhase
    && hiddenPreviewBlockIds.length === 0;
  const canAnalyze =
    !isSubmitting &&
    !isGeneratingRevision &&
    !isSavingDiffReview &&
    !isApplyingRevision &&
    !revisionWorkflowPending &&
    ((isReviewPhase && !canStopRun && appendableSelectedAgents.length > 0) ||
      (isIntakePhase && ((formState.sourceType === "url" && canAnalyzePreviewDocument) ||
        (formState.sourceType === "text" && formState.text.trim().length > 0) ||
        (formState.sourceType === "file" && selectedFile !== null))));
  const canGenerateRevision =
    artifact !== null
    && isTerminalArtifact
    && !canStopRun
    && hasAcceptedSuggestions
    && diffReview === null
    && !isGeneratingRevision
    && !isApplyingRevision;
  const reviewProgress = useMemo(() => {
    const revisionId = artifact?.document?.revision_id;
    if (!artifact || revisionId == null) return null;
    const agentComments = artifact.threads
      .filter((thread) => thread.document_revision_id === revisionId)
      .flatMap((thread) => thread.comments)
      .filter((comment) => comment.author_type !== "human" && comment.document_revision_id === revisionId);
    const reviewed = agentComments.filter((c) => c.review_state !== "unreviewed").length;
    return { reviewed, total: agentComments.length };
  }, [artifact]);
  const analyzeButtonLabel = revisionWorkflowPending
    ? "Apply revised markdown first"
    : isReviewPhase
      ? isFollowUpRunInProgress
        ? followUpRunLabel
        : "Add selected analysis"
      : "Analyze content";
  const latestResumeEvent = useMemo(
    () =>
      [...(artifact?.events ?? [])]
        .reverse()
        .find((event) => event.event_type === "run" && event.status === "resumed"),
    [artifact?.events],
  );
  const isProgressActive = artifact !== null && (artifact.status === "queued" || artifact.status === "running");
  const showRunningPanel = isRunningPhase;

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
    if (formState.sourceType === "artifact") return;

    if (revisionWorkflowPending) {
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: "Apply the reviewed revised markdown before queueing another analysis pass.",
      });
      return;
    }

    if (isTerminalArtifact && artifact !== null) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: "Queueing additional analysis..." });
      dispatch({ type: "SET_IS_SUBMITTING", value: true });
      try {
        const updatedArtifact = await appendAgents({
          artifactId: artifact.artifact_id,
          selectedAgents: formState.selectedAgents,
        });
        dispatch({ type: "SET_ARTIFACT", artifact: updatedArtifact });
        dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: updatedArtifact.artifact_id });
        dispatch({ type: "SET_FORM_STATE", formState: hydrateFormStateFromArtifact(formState, updatedArtifact) });
        dispatch({ type: "SET_STATUS_MESSAGE", message: "Additional analysis queued" });
      } catch (error) {
        dispatch({
          type: "SET_STATUS_MESSAGE",
          message: error instanceof Error ? error.message : "Could not queue additional analysis.",
        });
      } finally {
        dispatch({ type: "SET_IS_SUBMITTING", value: false });
      }
      return;
    }

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

      let payload;
      if (formState.sourceType === "file" && selectedFile !== null) {
        const fileText = await selectedFile.text();
        payload = {
          sourceType: "file" as const,
          sourceLabel: selectedFile.name,
          title: extractTitleFromText(fileText) || selectedFile.name,
          text: fileText,
          selectedAgents: resolveSelectedAgents(formState.selectedAgents, agents),
          persistenceMode: formState.persistenceMode,
          includeDebugTrace: formState.includeDebugTrace,
        };
      } else if (formState.sourceType === "url" && previewDocument !== null) {
        payload = {
          sourceType: "url" as const,
          sourceLabel: formState.url,
          title: formState.title || previewDocument.title,
          text: buildPreviewSubmissionText(previewDocument, hiddenPreviewBlockIds),
          url: formState.url,
          selectedAgents: resolveSelectedAgents(formState.selectedAgents, agents),
          persistenceMode: formState.persistenceMode,
          includeDebugTrace: formState.includeDebugTrace,
        };
      } else {
        payload = {
          sourceType: "text" as const,
          sourceLabel: formState.sourceLabel || "Manual input",
          title: extractTitleFromText(formState.text),
          text: formState.text,
          selectedAgents: resolveSelectedAgents(formState.selectedAgents, agents),
          persistenceMode: formState.persistenceMode,
          includeDebugTrace: formState.includeDebugTrace,
        };
      }

      const createdArtifact = await createRun(payload, signal);
      dispatch({ type: "SET_ARTIFACT", artifact: createdArtifact });
      dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: createdArtifact.artifact_id });
      dispatch({ type: "SET_FORM_STATE", formState: hydrateFormStateFromArtifact(formState, createdArtifact) });
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
      dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: activeArtifactIdFor(imported) });
      dispatch({ type: "SET_FORM_STATE", formState: hydrateFormStateFromArtifact(formState, imported) });
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

  async function handleReply(comment: ArtifactComment) {
    if (artifact === null) {
      return;
    }
    const body = replyDrafts[comment.id]?.trim();
    if (!body) {
      return;
    }

    dispatch({ type: "SET_IS_SUBMITTING", value: true });
    try {
      if (comment.category === "research") {
        const updatedArtifact = await queueResearch({
          artifactId: artifact.artifact_id,
          prompt: body,
          anchorId: comment.anchor_id,
          commentId: comment.id,
        });
        dispatch({ type: "SET_ARTIFACT", artifact: updatedArtifact });
        dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: updatedArtifact.artifact_id });
      } else {
        await addReply(comment.id, body);
        await refreshArtifact(artifact.artifact_id);
      }
      dispatch({ type: "SET_REPLY_DRAFT", commentId: comment.id, body: "" });
      dispatch({ type: "SET_ACTIVE_REPLY_COMPOSER", commentId: null });
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: comment.category === "research" ? "Follow-up research queued" : "Comment saved",
      });
    } catch (error) {
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: error instanceof Error ? error.message : "Could not save reply.",
      });
    } finally {
      dispatch({ type: "SET_IS_SUBMITTING", value: false });
    }
  }

  async function handleQueueResearch(prompt: string) {
    if (artifact === null) {
      return;
    }
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      return;
    }

    setIsQueuingResearch(true);
    try {
      const updatedArtifact = await queueResearch({
        artifactId: artifact.artifact_id,
        prompt: trimmedPrompt,
      });
      dispatch({ type: "SET_ARTIFACT", artifact: updatedArtifact });
      dispatch({ type: "SET_ACTIVE_ARTIFACT_ID", id: updatedArtifact.artifact_id });
      dispatch({ type: "SET_STATUS_MESSAGE", message: "Targeted research queued" });
    } catch (error) {
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: error instanceof Error ? error.message : "Could not queue targeted research.",
      });
    } finally {
      setIsQueuingResearch(false);
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

  async function handleGenerateRevision(mode: RevisionMode) {
    if (artifact === null || !canGenerateRevision) {
      return;
    }
    const trimmedDirectionPrompt = rewriteDirectionPrompt.trim();
    if (mode === "rewrite" && !trimmedDirectionPrompt) {
      dispatch({ type: "SET_STATUS_MESSAGE", message: "Add a direction before generating a rewrite draft." });
      return;
    }
    dispatch({ type: "SET_IS_GENERATING_REVISION", value: true });
    dispatch({
      type: "SET_STATUS_MESSAGE",
      message: mode === "rewrite" ? "Generating rewrite draft..." : "Applying accepted changes...",
    });
    try {
      const updatedArtifact = await generateRevisedMarkdown({
        artifactId: artifact.artifact_id,
        mode,
        directionPrompt: mode === "rewrite" ? trimmedDirectionPrompt : undefined,
      });
      dispatch({ type: "SET_ARTIFACT", artifact: updatedArtifact });
      setRewritePromptOpen(false);
      if (mode === "rewrite") {
        setRewriteDirectionPrompt("");
      }
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: mode === "rewrite" ? "Rewrite draft ready for diff review." : "Surgical revision ready for diff review.",
      });
    } catch (error) {
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: error instanceof Error ? error.message : "Could not generate revised markdown.",
      });
    } finally {
      dispatch({ type: "SET_IS_GENERATING_REVISION", value: false });
    }
  }

  async function handleDiffDecision(diffId: string, decision: "accepted" | "rejected") {
    if (artifact === null) {
      return;
    }
    dispatch({ type: "SET_IS_SAVING_DIFF_REVIEW", value: true });
    try {
      const updatedArtifact = await updateRevisedMarkdownDiffReview(artifact.artifact_id, [
        { diffId, decision },
      ]);
      dispatch({ type: "SET_ARTIFACT", artifact: updatedArtifact });
      dispatch({ type: "SET_STATUS_MESSAGE", message: "Saved revised markdown diff decision." });
    } catch (error) {
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: error instanceof Error ? error.message : "Could not save the diff review decision.",
      });
    } finally {
      dispatch({ type: "SET_IS_SAVING_DIFF_REVIEW", value: false });
    }
  }

  async function handleApplyRevision() {
    if (artifact === null || diffReview === null || isRevisedMarkdownPending(diffReview)) {
      return;
    }
    dispatch({ type: "SET_IS_APPLYING_REVISION", value: true });
    dispatch({ type: "SET_STATUS_MESSAGE", message: "Applying reviewed revised markdown..." });
    try {
      const updatedArtifact = await applyRevisedMarkdown(artifact.artifact_id);
      setRewritePromptOpen(false);
      setRewriteDirectionPrompt("");
      dispatch({ type: "SET_ARTIFACT", artifact: updatedArtifact });
      dispatch({
        type: "SET_FORM_STATE",
        formState: hydrateFormStateAfterRevision(formState, updatedArtifact, agents),
      });
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: "Reviewed revised markdown promoted to the working draft.",
      });
    } catch (error) {
      dispatch({
        type: "SET_STATUS_MESSAGE",
        message: error instanceof Error ? error.message : "Could not apply the revised markdown.",
      });
    } finally {
      dispatch({ type: "SET_IS_APPLYING_REVISION", value: false });
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <ReviewHero />

        {isIntakePhase ? (
          <>
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
              canStopRun={false}
              canExport={false}
              canGenerateRevision={false}
              showGenerateRevision={false}
              generatingRevision={isGeneratingRevision}
              showNewAnalysis={false}
              analyzeButtonLabel={analyzeButtonLabel}
              disabledAgentIds={[...completedAgentIds]}
              lockedAgentIds={completedAgentIds.has("fact_check") ? ["fact_check"] : []}
              importInputKey={importInputKey}
              showUrlImportGuidance={showUrlImportGuidance}
              hasLoadedContent={false}
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
                  }),
                });
              }}
              onImportFileChange={handleImportFile}
              onPreviewUrl={handlePreviewUrl}
              onSubmit={handleSubmit}
              onGenerateRevision={() => void handleGenerateRevision("surgical")}
              onStopRun={handleStopRun}
              onStartNewAnalysis={handleStartNewAnalysis}
              onExport={handleExport}
            />

            {displayDocument !== null ? (
              <section className={styles.intakePreviewShell} data-testid="intake-preview-shell">
                <DocumentPane
                document={displayDocument}
                anchors={[]}
                threads={[]}
                anchorThreadMap={new Map<string, { colors: string[] }>()}
                activeDocumentRevisionId={null}
                selectionEnabled={false}
                  hoveredAnchorId={null}
                  hiddenBlockIds={hiddenPreviewBlockIds}
                  previewPruningEnabled={formState.sourceType === "url" && previewDocument !== null}
                  anchorRefs={anchorRefs}
                  commentRefs={commentRefs}
                  onHoverAnchor={() => undefined}
                  onSelectionDraft={() => undefined}
                  onHideBlock={(blockId) => dispatch({ type: "HIDE_PREVIEW_BLOCK", blockId })}
                  onRestoreBlock={(blockId) => dispatch({ type: "RESTORE_PREVIEW_BLOCK", blockId })}
                  onRestoreAllBlocks={() => dispatch({ type: "RESTORE_ALL_PREVIEW_BLOCKS" })}
                  replyDrafts={replyDrafts}
                  activeReplyComposerId={activeReplyComposerId}
                  editingCommentId={editingCommentId}
                  editingBody={editingBody}
                  onReplyDraftChange={() => undefined}
                  onToggleReplyComposer={() => undefined}
                  onAddReply={() => undefined}
                  onDeleteReply={() => undefined}
                  onReviewState={() => undefined}
                  onStartEditing={() => undefined}
                  onEditingBodyChange={() => undefined}
                  onSaveEdit={() => undefined}
                  onCancelEdit={() => undefined}
                  onDeleteComment={() => undefined}
                />
              </section>
            ) : null}
          </>
        ) : null}

        {artifact?.error_message ? <section className={styles.errorBanner}>{artifact.error_message}</section> : null}

        {showRunningPanel ? (
          <RunningStagePanel
            progress={progress}
            status={artifact?.status ?? "running"}
            latestResumeEvent={latestResumeEvent}
            agentPlan={artifact?.agent_plan ?? []}
            agentResults={artifact?.agent_results ?? []}
            events={artifact?.events ?? []}
            onStopRun={handleStopRun}
            canStopRun={canStopRun}
          />
        ) : null}

        {isReviewPhase ? (
          <>
            <ReviewToolbar
              formState={formState}
              agents={agents}
              fileInputKey={fileInputKey}
              selectedFile={selectedFile}
              statusMessage={statusMessage}
              submitting={isSubmitting}
              previewing={isPreviewing}
              canAnalyze={canAnalyze}
              canPreviewUrl={false}
              canStopRun={canStopRun}
              canExport={canExport}
              canGenerateRevision={canGenerateRevision}
              showGenerateRevision={artifact !== null && isTerminalArtifact && hasAcceptedSuggestions && diffReview === null}
              generatingRevision={isGeneratingRevision}
              showNewAnalysis={showNewAnalysis}
              analyzeButtonLabel={analyzeButtonLabel}
              disabledAgentIds={[...completedAgentIds]}
              lockedAgentIds={completedAgentIds.has("fact_check") ? ["fact_check"] : []}
              importInputKey={importInputKey}
              showUrlImportGuidance={false}
              hasLoadedContent={true}
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
                  }),
                });
              }}
              onImportFileChange={handleImportFile}
              onPreviewUrl={handlePreviewUrl}
              onSubmit={handleSubmit}
              onGenerateRevision={() => void handleGenerateRevision("surgical")}
              onStopRun={handleStopRun}
              onStartNewAnalysis={handleStartNewAnalysis}
              onExport={handleExport}
            />

            <SelectionBanner
              selectionDraft={selectionDraft}
              commentDraft={commentDraft}
              onCommentDraftChange={(value) => dispatch({ type: "SET_COMMENT_DRAFT", draft: value })}
              onSave={handleCreateComment}
              onCancel={() => dispatch({ type: "SET_SELECTION_DRAFT", draft: null })}
            />

            {artifact !== null && !isFollowUpRunInProgress && isTerminalArtifact && hasAcceptedSuggestions && diffReview === null ? (
              <RevisionActions
                location="top"
                canGenerateRevision={canGenerateRevision}
                generatingRevision={isGeneratingRevision}
                rewritePromptOpen={rewritePromptOpen}
                rewriteDirectionPrompt={rewriteDirectionPrompt}
                onRewriteDirectionPromptChange={setRewriteDirectionPrompt}
                onToggleRewritePrompt={() => setRewritePromptOpen((current) => !current)}
                onApplyChanges={() => void handleGenerateRevision("surgical")}
                onRewriteDraft={() => void handleGenerateRevision("rewrite")}
              />
            ) : null}

            {artifact !== null && isFollowUpRunInProgress ? (
              <section className={styles.reviewInlineProgress} data-testid="follow-up-progress">
                <div className={styles.reviewInlineProgressMeta}>
                  <span className={styles.pill}>{followUpRunLabel}</span>
                  <span className={styles.reviewInlineProgressStatus}>{artifact.status}</span>
                </div>
                <div
                  className={`${styles.progressTrack} ${isProgressActive ? styles.progressTrackActive : ""}`}
                  data-testid="compact-progress-track"
                  aria-hidden="true"
                >
                  <div
                    className={`${styles.progressFill} ${isProgressActive ? styles.progressFillActive : ""}`}
                    data-testid="compact-progress-fill"
                    style={{ width: `${Math.round(progress * 100)}%` }}
                  />
                </div>
                <div className={styles.progressMeta}>
                  <span>{Math.round(progress * 100)}% complete</span>
                  <button className={styles.stateButton} type="button" onClick={handleStopRun} disabled={!canStopRun}>
                    Stop run
                  </button>
                </div>
              </section>
            ) : null}

            {artifact !== null && artifact.summary !== null && !isFollowUpRunInProgress ? (
              <RunMetrics summary={artifact.summary} />
            ) : null}
            <ReviewSummaryPanel reviewSummary={artifact?.review_summary ?? null} />
            {hasHistoricalFindings ? (
              <section className={styles.historicalNotice} data-testid="historical-findings-indicator">
                Fact-check and research findings below reflect the previous draft. They are preserved as historical context and do not count as current-draft revision input.
              </section>
            ) : null}
            {artifact !== null ? (
              <ResearchPanel
                key={artifact.artifact_id}
                initialPrompt={researchPromptSeed}
                disabled={isSubmitting || isQueuingResearch || isFollowUpRunInProgress}
                submitting={isSubmitting || isQueuingResearch}
                onSubmit={handleQueueResearch}
              />
            ) : null}
            <section className={styles.analysisContextPanel}>
              <AgentUsageSummary
                agentResults={artifact?.agent_results ?? []}
                agentPlan={artifact?.agent_plan ?? []}
              />
            </section>

            <section className={styles.workspace} ref={workspaceRef} data-testid="review-workbench">
              {reviewProgress !== null && reviewProgress.total > 0 ? (
                <div className={styles.reviewProgressBar}>
                  <span className={styles.pill}>
                    {reviewProgress.reviewed} of {reviewProgress.total} comments reviewed
                  </span>
                </div>
              ) : null}
              <DocumentPane
                document={displayDocument}
                anchors={artifact?.anchors ?? []}
                threads={normalizedThreads}
                anchorThreadMap={anchorThreadMap}
                activeDocumentRevisionId={currentRevisionId}
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

            {previousDraftSnapshot !== null && historicalSnapshotThreads.length > 0 ? (
              <section className={styles.historicalSection} data-testid="historical-findings-panel">
                <div className={styles.historicalSectionHeader}>
                  <h2 className={styles.sectionTitle}>Original-draft findings</h2>
                  <p className={styles.reviewSummaryText}>
                    These preserved fact-check and research findings no longer map cleanly into the current draft, so they remain attached to the archived previous draft.
                  </p>
                </div>
                <DocumentPane
                  document={previousDraftSnapshot.document}
                  anchors={previousDraftSnapshot.anchors}
                  threads={historicalSnapshotThreads}
                  anchorThreadMap={historicalAnchorThreadMap}
                  activeDocumentRevisionId={currentRevisionId}
                  selectionEnabled={false}
                  hoveredAnchorId={hoveredAnchorId}
                  hiddenBlockIds={[]}
                  previewPruningEnabled={false}
                  anchorRefs={historicalAnchorRefs}
                  commentRefs={historicalCommentRefs}
                  onHoverAnchor={(anchorId) => dispatch({ type: "SET_HOVERED_ANCHOR_ID", anchorId })}
                  onSelectionDraft={() => undefined}
                  onHideBlock={() => undefined}
                  onRestoreBlock={() => undefined}
                  onRestoreAllBlocks={() => undefined}
                  replyDrafts={{}}
                  editingCommentId={null}
                  editingBody=""
                  onReplyDraftChange={() => undefined}
                  activeReplyComposerId={null}
                  onToggleReplyComposer={() => undefined}
                  onAddReply={() => undefined}
                  onDeleteReply={() => undefined}
                  onReviewState={() => undefined}
                  onStartEditing={() => undefined}
                  onEditingBodyChange={() => undefined}
                  onSaveEdit={() => undefined}
                  onCancelEdit={() => undefined}
                  onDeleteComment={() => undefined}
                />
              </section>
            ) : null}
          </>
        ) : null}

        {isDiffReviewPhase && diffReview !== null ? (
          <section className={styles.diffReviewShell} data-testid="diff-review-shell">
            <RevisedMarkdownPanel
              originalMarkdown={diffReview.originalMarkdown}
              candidateMarkdown={diffReview.candidateMarkdown}
              mode={diffReview.mode}
              directionPrompt={diffReview.directionPrompt}
              diffItems={diffReview.diffItems}
              applied={revisedMarkdownApplied}
              savingDecision={isSavingDiffReview}
              applyingRevision={isApplyingRevision}
              onDecisionChange={handleDiffDecision}
              onApply={handleApplyRevision}
            />
          </section>
        ) : null}
      </div>
    </main>
  );
}

function ResearchPanel({
  initialPrompt,
  disabled,
  submitting,
  onSubmit,
}: {
  initialPrompt: string;
  disabled: boolean;
  submitting: boolean;
  onSubmit: (prompt: string) => void;
}) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const canSubmit = prompt.trim().length > 0 && !disabled && !submitting;

  return (
    <section className={styles.researchPanel} data-testid="research-panel">
      <div className={styles.researchPanelHeader}>
        <div className={styles.researchPanelHeaderText}>
          <span className={styles.metricLabel}>Research</span>
          <p className={styles.researchPanelCopy}>
            Ask for a targeted follow-up while staying in the review shell.
          </p>
        </div>
        <span className={styles.pill}>{initialPrompt ? "Suggested prompt loaded" : "Empty prompt"}</span>
      </div>
      <div className={styles.researchPanelBody}>
        <textarea
          className={styles.researchPromptInput}
          aria-label="Research prompt"
          rows={2}
          value={prompt}
          placeholder="Ask a targeted research question"
          onChange={(event) => setPrompt(event.target.value)}
        />
        <div className={styles.researchPanelActions}>
          <button
            className={styles.button}
            type="button"
            onClick={() => onSubmit(prompt)}
            disabled={!canSubmit}
            data-testid="research-submit-button"
          >
            {submitting ? "Researching..." : "Research"}
          </button>
          <span className={styles.researchPanelHint}>
            {initialPrompt
              ? "Loaded from fact-check metadata when available."
              : "Start from an empty prompt if no fact-check suggestion exists."}
          </span>
        </div>
      </div>
    </section>
  );
}

function RevisionActions({
  location,
  canGenerateRevision,
  generatingRevision,
  rewritePromptOpen,
  rewriteDirectionPrompt,
  onRewriteDirectionPromptChange,
  onToggleRewritePrompt,
  onApplyChanges,
  onRewriteDraft,
}: {
  location: "top" | "bottom";
  canGenerateRevision: boolean;
  generatingRevision: boolean;
  rewritePromptOpen: boolean;
  rewriteDirectionPrompt: string;
  onRewriteDirectionPromptChange: (value: string) => void;
  onToggleRewritePrompt: () => void;
  onApplyChanges: () => void;
  onRewriteDraft: () => void;
}) {
  return (
    <section className={styles.revisionCta} data-testid={`revision-cta-${location}`}>
      <div className={styles.revisionCtaHeader}>
        <span>Choose how to revise the current draft</span>
        <span className={styles.revisionCtaHint}>Historical findings are excluded from this step.</span>
      </div>
      <div className={styles.revisionCtaActions}>
        <button
          className={styles.button}
          data-testid="apply-changes-button"
          type="button"
          onClick={onApplyChanges}
          disabled={!canGenerateRevision || generatingRevision}
        >
          {generatingRevision ? "Generating..." : "Apply changes"}
        </button>
        <button
          className={styles.ghostButton}
          data-testid="rewrite-draft-button"
          type="button"
          onClick={onToggleRewritePrompt}
          disabled={!canGenerateRevision || generatingRevision}
        >
          {rewritePromptOpen ? "Cancel rewrite" : "Rewrite draft"}
        </button>
      </div>
      {rewritePromptOpen ? (
        <div className={styles.rewriteComposer}>
          <textarea
            className={styles.researchPromptInput}
            data-testid="rewrite-direction-input"
            aria-label="Rewrite direction"
            rows={3}
            value={rewriteDirectionPrompt}
            placeholder="Give the rewrite a direction, such as leading with the strongest finding or tightening the structure."
            onChange={(event) => onRewriteDirectionPromptChange(event.target.value)}
          />
          <div className={styles.rewriteComposerActions}>
            <button
              className={styles.button}
              data-testid="submit-rewrite-draft-button"
              type="button"
              onClick={onRewriteDraft}
              disabled={!canGenerateRevision || generatingRevision || rewriteDirectionPrompt.trim().length === 0}
            >
              {generatingRevision ? "Generating..." : "Generate rewrite"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function RunningStagePanel({
  progress,
  status,
  latestResumeEvent,
  agentPlan,
  agentResults,
  events,
  onStopRun,
  canStopRun,
}: {
  progress: number;
  status: RunStatus;
  latestResumeEvent: ArtifactEvent | undefined;
  agentPlan: AnalysisArtifact["agent_plan"];
  agentResults: AnalysisArtifact["agent_results"];
  events: AnalysisArtifact["events"];
  onStopRun: () => void;
  canStopRun: boolean;
}) {
  const findings = useMemo(
    () =>
          agentResults.flatMap((result) =>
            result.findings.map((finding) => ({
              agentId: result.agent_id,
              category: result.category,
              rationale: finding.rationale,
              suggestion: finding.suggestion,
              confidence: finding.confidence,
              sources: finding.sources ?? [],
              metadata: finding.metadata,
            })),
          ),
    [agentResults],
  );

  return (
    <section className={styles.progressPanel} data-testid="running-stage-panel">
      <div className={styles.sectionTitle}>Run progress</div>
      <div
        className={`${styles.progressTrack} ${styles.progressTrackActive}`}
        data-testid="progress-track"
        aria-hidden="true"
      >
        <div
          className={`${styles.progressFill} ${styles.progressFillActive}`}
          data-testid="progress-fill"
          style={{ width: `${Math.round(progress * 100)}%` }}
        />
      </div>
      <div className={styles.progressMeta}>
        <span>{Math.round(progress * 100)}% complete</span>
        <span>{status}</span>
      </div>
      {latestResumeEvent ? (
        <div className={styles.progressNote} data-testid="run-resumed-note">
          {latestResumeEvent.message}
          {latestResumeEvent.attempt ? ` (${latestResumeEvent.attempt}${latestResumeEvent.max_attempts ? ` of ${latestResumeEvent.max_attempts}` : ""})` : ""}
        </div>
      ) : null}
      <RunningFindingsPreview findings={findings} />
      <div className={styles.agentStatusGrid}>
        {agentPlan.map((item) => (
          <article key={item.agent_id} className={styles.agentStatusCard} data-testid={`agent-plan-${item.agent_id}`}>
            <strong>{item.display_name}</strong>
            <span className={styles.pill}>{item.status}</span>
            <p className={styles.agentStatusCopy}>{item.message ?? item.category}</p>
          </article>
        ))}
      </div>
      <hr className={styles.runDetailsDivider} />
      <AgentUsageSummary agentResults={agentResults} agentPlan={agentPlan} />
      <hr className={styles.runDetailsDivider} />
      <details className={styles.runLogDetails}>
        <summary className={styles.runLogToggle}>Run log ({events.length} events)</summary>
        <CommentRail events={events} />
      </details>
      <div className={styles.runningStageActions}>
        <button className={styles.ghostButton} type="button" onClick={onStopRun} disabled={!canStopRun}>
          Stop run
        </button>
      </div>
    </section>
  );
}

function RunningFindingsPreview({
  findings,
}: {
  findings: Array<{
    agentId: string;
    category: AnalysisArtifact["agent_results"][number]["category"];
    rationale: string;
    suggestion: string | null | undefined;
    confidence: number;
    sources: string[];
    metadata: Record<string, unknown>;
  }>;
}) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (findings.length <= 1) {
      setIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % findings.length);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [findings.length]);

  useEffect(() => {
    if (index >= findings.length) {
      setIndex(0);
    }
  }, [findings.length, index]);

  if (!findings.length) {
    return (
      <article className={styles.runningPreviewCard} data-testid="running-preview-card">
        <div className={styles.metricLabel}>Partial findings</div>
        <p className={styles.reviewSummaryText}>Waiting for the first agent result.</p>
      </article>
    );
  }

  const item = findings[index % findings.length];

  return (
    <article className={styles.runningPreviewCard} data-testid="running-preview-card">
      <div className={styles.runningPreviewMeta}>
        <span className={styles.pill}>{item.category}</span>
        <span className={styles.reviewBadge}>
          Finding {index + 1} of {findings.length}
        </span>
      </div>
      <p className={styles.runningPreviewText}>{item.rationale}</p>
      {item.suggestion ? <p className={styles.runningPreviewSuggestion}>{item.suggestion}</p> : null}
      <div className={styles.runningPreviewFootnote}>
        <span>{item.confidence.toFixed(2)} confidence</span>
        <span>{item.sources.length} sources</span>
      </div>
    </article>
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

type DiffDecision = "pending" | "accepted" | "rejected";

interface ArtifactDiffItemView {
  id: string;
  changeType: string;
  beforeText: string;
  afterText: string;
  decision: DiffDecision;
  originalStartLine: number;
  originalEndLine: number;
  candidateStartLine: number;
  candidateEndLine: number;
}

interface ArtifactDiffReviewView {
  mode: RevisionMode;
  directionPrompt: string | null;
  originalMarkdown: string;
  candidateMarkdown: string;
  diffItems: ArtifactDiffItemView[];
}

function hasAcceptedRevisionSuggestions(artifact: AnalysisArtifact | null): boolean {
  const currentRevisionId = artifact?.document?.revision_id;
  if (artifact === null || currentRevisionId == null) {
    return false;
  }
  return artifact.threads.some((thread) =>
    thread.comments.some(
      (comment) =>
        comment.document_revision_id === currentRevisionId
        && thread.document_revision_id === currentRevisionId
        && comment.author_type === "agent"
        && comment.review_state === "accepted"
        && typeof comment.suggestion === "string"
        && comment.suggestion.trim().length > 0,
    ),
  );
}

function getArtifactDiffReview(artifact: AnalysisArtifact | null): ArtifactDiffReviewView | null {
  if (artifact === null) {
    return null;
  }
  const diffReview = artifact.diff_review;
  if (diffReview === null || diffReview === undefined) {
    return null;
  }

  return {
    mode: diffReview.mode,
    directionPrompt: diffReview.direction_prompt ?? null,
    originalMarkdown: diffReview.original_markdown,
    candidateMarkdown: diffReview.candidate_markdown,
    diffItems: diffReview.diff_items.flatMap((item) => toDiffItemView(item)),
  };
}

function normalizeThreads(document: ArtifactDocument | null, threads: ArtifactThread[]): ArtifactThread[] {
  if (document === null) {
    return [];
  }

  const blockIndexById = new Map(document.blocks.map((block) => [block.id, block.index]));
  return [...threads]
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
}

function buildAnchorThreadMap(
  threads: ArtifactThread[],
  agentResults: AnalysisArtifact["agent_results"],
): Map<string, { colors: string[] }> {
  const map = new Map<string, { colors: string[] }>();
  threads.forEach((thread) => {
    map.set(thread.anchor.id, {
      colors: thread.comments.map((comment) => categoryColors[comment.category] ?? "var(--ink)"),
    });
  });
  agentResults.forEach((result) => {
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
}

function isHistoricalThread(thread: ArtifactThread, currentRevisionId: string | null): boolean {
  if (currentRevisionId == null) {
    return false;
  }
  return thread.document_revision_id != null && thread.document_revision_id !== currentRevisionId;
}

function toDiffItemView(value: unknown): ArtifactDiffItemView[] {
  if (typeof value !== "object" || value === null) {
    return [];
  }
  const record = value as Record<string, unknown>;
  return [
    {
      id: typeof record.id === "string" ? record.id : "diff-item",
      changeType: typeof record.change_type === "string" ? record.change_type : "replace",
      beforeText: typeof record.before_text === "string" ? record.before_text : "",
      afterText: typeof record.after_text === "string" ? record.after_text : "",
      decision: isDiffDecision(record.decision) ? record.decision : "pending",
      originalStartLine: typeof record.original_start_line === "number" ? record.original_start_line : 0,
      originalEndLine: typeof record.original_end_line === "number" ? record.original_end_line : 0,
      candidateStartLine: typeof record.candidate_start_line === "number" ? record.candidate_start_line : 0,
      candidateEndLine: typeof record.candidate_end_line === "number" ? record.candidate_end_line : 0,
    },
  ];
}

function isDiffDecision(value: unknown): value is DiffDecision {
  return value === "pending" || value === "accepted" || value === "rejected";
}

function isRevisedMarkdownPending(diffReview: ArtifactDiffReviewView): boolean {
  return diffReview.diffItems.some((item) => item.decision === "pending");
}

function isRevisedMarkdownApplied(artifact: AnalysisArtifact | null): boolean {
  if (artifact === null) {
    return false;
  }
  return [...artifact.events]
    .reverse()
    .some((event) => event.stage === "revised_markdown" && event.status === "applied");
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
    (candidate.sourceType === "text" || candidate.sourceType === "url"
      || candidate.sourceType === "file" || candidate.sourceType === "artifact")
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

function hydrateFormStateAfterRevision(
  current: ReviewFormState,
  artifact: AnalysisArtifact,
  agents: AgentCatalogEntry[],
): ReviewFormState {
  const next = hydrateFormStateFromArtifact(current, artifact);
  const rerunDefaults = ["ai_likelihood", "editorial"].filter((agentId) =>
    agents.some((agent) => agent.agent_id === agentId),
  );
  if (!rerunDefaults.length) {
    return next;
  }
  return {
    ...next,
    selectedAgents: resolveSelectedAgents(rerunDefaults, agents),
  };
}

function extractTitleFromText(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  for (const line of trimmed.split("\n")) {
    const match = /^#\s+(.+)$/.exec(line.trim());
    if (match) return match[1].trim();
  }
  const first = trimmed.split("\n").find((l) => l.trim().length > 0) ?? "";
  return first.length > 80 ? first.slice(0, 77) + "..." : first.trim();
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

function getWorkbenchPhase(artifact: AnalysisArtifact | null): WorkbenchPhase {
  if (artifact === null || artifact.status === "draft") {
    return "intake";
  }
  if (artifact.diff_review != null && !isRevisedMarkdownApplied(artifact)) {
    return "diff_review";
  }
  if ((artifact.status === "queued" || artifact.status === "running") && getFollowUpRunMode(artifact) === null) {
    return "running";
  }
  return "review";
}

type FollowUpRunMode = "append_agents" | "research";

function getFollowUpRunMode(artifact: AnalysisArtifact | null): FollowUpRunMode | null {
  if (artifact === null) {
    return null;
  }

  for (const event of [...artifact.events].reverse()) {
    if (event.event_type !== "run") {
      continue;
    }
    const metadata = event.metadata as { mode?: unknown };
    if (metadata.mode === "research") {
      return "research";
    }
    if (metadata.mode === "append_agents" || event.message.includes("Additional analysis")) {
      return "append_agents";
    }
  }

  return null;
}

function getSuggestedResearchPrompt(artifact: AnalysisArtifact | null): string {
  if (artifact === null) {
    return "";
  }

  for (const result of artifact.agent_results) {
    if (result.category !== "fact_check") {
      continue;
    }
    const prompt = result.metadata?.suggested_research_prompt;
    if (typeof prompt === "string" && prompt.trim().length > 0) {
      return prompt.trim();
    }
  }

  return "";
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
