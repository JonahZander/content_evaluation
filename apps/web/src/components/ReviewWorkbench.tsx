"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { CommentRail } from "@/components/review/CommentRail";
import { DocumentPane } from "@/components/review/DocumentPane";
import { ReviewHero } from "@/components/review/ReviewHero";
import { ReviewToolbar, type ReviewFormState } from "@/components/review/ReviewToolbar";
import { RunMetrics } from "@/components/review/RunMetrics";
import { SelectionBanner } from "@/components/review/SelectionBanner";
import { categoryColors } from "@/components/review/category-colors";
import {
  addReply,
  createComment,
  createRun,
  deleteHumanComment,
  fetchAgents,
  fetchArtifact,
  getExportUrl,
  importArtifact,
  updateHumanComment,
  updateReviewState,
} from "@/lib/api";
import type { AgentCatalogEntry, AnalysisArtifact, ArtifactThread, ReviewState } from "@/lib/types";

interface SelectionDraft {
  blockId: string;
  startOffset: number;
  endOffset: number;
  quote: string;
}

interface ReviewWorkbenchProps {
  initialArtifact: AnalysisArtifact | null;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const SESSION_STORAGE_KEY = "content-evaluation:artifact";

export function ReviewWorkbench({ initialArtifact }: ReviewWorkbenchProps) {
  const [artifact, setArtifact] = useState<AnalysisArtifact | null>(initialArtifact);
  const [agents, setAgents] = useState<AgentCatalogEntry[]>([]);
  const [statusMessage, setStatusMessage] = useState("Choose content, choose agents, and start a session.");
  const [hoveredAnchorId, setHoveredAnchorId] = useState<string | null>(null);
  const [selectionDraft, setSelectionDraft] = useState<SelectionDraft | null>(null);
  const [commentDraft, setCommentDraft] = useState("");
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  const [editingBody, setEditingBody] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [importInputKey, setImportInputKey] = useState(0);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(initialArtifact?.artifact_id ?? null);
  const [formState, setFormState] = useState<ReviewFormState>({
    sourceType: "text",
    title: "",
    sourceLabel: "Manual input",
    text: "",
    url: "",
    persistenceMode: "session",
    includeDebugTrace: true,
    selectedAgents: [],
  });

  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const anchorRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const commentRefs = useRef<Record<string, HTMLElement | null>>({});

  useEffect(() => {
    fetchAgents()
      .then((catalog) => {
        setAgents(catalog);
        setFormState((current) =>
          current.selectedAgents.length
            ? current
            : {
                ...current,
                selectedAgents: catalog.filter((agent) => agent.default_enabled).map((agent) => agent.agent_id),
              },
        );
      })
      .catch(() => {
        setStatusMessage("Could not load the agent catalog.");
      });
  }, []);

  useEffect(() => {
    if (initialArtifact !== null) {
      return;
    }
    if (typeof window === "undefined") {
      return;
    }
    const stored = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!stored) {
      return;
    }
    try {
      const parsed = JSON.parse(stored) as AnalysisArtifact;
      setArtifact(parsed);
      setActiveArtifactId(parsed.status === "running" || parsed.status === "queued" ? parsed.artifact_id : null);
      setStatusMessage(`Restored ${parsed.status} artifact from this browser session.`);
      setFormState((current) => ({
        ...current,
        title: parsed.document?.title ?? parsed.source.title ?? current.title,
        text: parsed.document?.text ?? current.text,
        selectedAgents: parsed.run_config.selected_agents,
        persistenceMode: parsed.run_config.persistence_mode,
        includeDebugTrace: parsed.run_config.include_debug_trace,
      }));
    } catch {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }, [initialArtifact]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (artifact === null) {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      return;
    }
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(artifact));
  }, [artifact]);

  async function refreshArtifact(artifactId: string) {
    const updated = await fetchArtifact(artifactId);
    setArtifact(updated);
    setStatusMessage(`Run ${updated.status}`);
    return updated;
  }

  useEffect(() => {
    if (!activeArtifactId) {
      return;
    }

    const eventSource = new EventSource(`${API_BASE_URL}/api/v1/runs/${activeArtifactId}/events`);
    eventSource.onmessage = async (event) => {
      const parsed = JSON.parse(event.data) as { snapshot_available?: boolean };
      if (parsed.snapshot_available) {
        const updated = await refreshArtifact(activeArtifactId);
        if (updated.status === "completed" || updated.status === "failed") {
          setActiveArtifactId(null);
          eventSource.close();
        }
      }
    };
    eventSource.onerror = () => {
      setStatusMessage("Live artifact updates disconnected. Refreshing on the next action.");
      eventSource.close();
    };
    return () => eventSource.close();
  }, [activeArtifactId]);

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
        const leftBlockIndex = blockIndexById.get(left.anchor.block_id) ?? Number.MAX_SAFE_INTEGER;
        const rightBlockIndex = blockIndexById.get(right.anchor.block_id) ?? Number.MAX_SAFE_INTEGER;
        if (leftBlockIndex !== rightBlockIndex) {
          return leftBlockIndex - rightBlockIndex;
        }
        if (left.anchor.start_offset !== right.anchor.start_offset) {
          return left.anchor.start_offset - right.anchor.start_offset;
        }
        if (left.anchor.end_offset !== right.anchor.end_offset) {
          return left.anchor.end_offset - right.anchor.end_offset;
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

  async function handleSubmit() {
    setStatusMessage("Submitting analysis session...");
    setIsSubmitting(true);
    try {
      if (formState.sourceType === "file" && selectedFile !== null && !/\.(txt|md)$/i.test(selectedFile.name)) {
        setStatusMessage("Only .txt and .md uploads are supported");
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
          : {
              sourceType: formState.sourceType,
              sourceLabel: formState.sourceLabel || (formState.sourceType === "url" ? formState.url : "Manual input"),
              title: formState.title,
              text: formState.text,
              url: formState.url,
              selectedAgents: resolveSelectedAgents(formState.selectedAgents, agents),
              persistenceMode: formState.persistenceMode,
              includeDebugTrace: formState.includeDebugTrace,
            };

      const createdArtifact = await createRun(payload);
      setArtifact(createdArtifact);
      setActiveArtifactId(createdArtifact.artifact_id);
      setSelectionDraft(null);
      setCommentDraft("");
      setEditingCommentId(null);
      setStatusMessage(`Artifact ${createdArtifact.artifact_id} queued`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not submit run");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleImportFile(file: File | null) {
    if (file === null) {
      return;
    }
    try {
      const parsed = JSON.parse(await file.text()) as AnalysisArtifact;
      const imported = await importArtifact(parsed);
      setArtifact(imported);
      setActiveArtifactId(null);
      setStatusMessage(`Imported artifact ${imported.artifact_id}`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not import artifact");
    } finally {
      setImportInputKey((current) => current + 1);
    }
  }

  async function handleCreateComment() {
    if (artifact === null || selectionDraft === null || !commentDraft.trim()) {
      return;
    }
    await createComment({
      artifactId: artifact.artifact_id,
      body: commentDraft,
      blockId: selectionDraft.blockId,
      startOffset: selectionDraft.startOffset,
      endOffset: selectionDraft.endOffset,
      quote: selectionDraft.quote,
    });
    await refreshArtifact(artifact.artifact_id);
    setSelectionDraft(null);
    setCommentDraft("");
  }

  async function handleReply(commentId: string) {
    if (artifact === null) {
      return;
    }
    const body = replyDrafts[commentId]?.trim();
    if (!body) {
      return;
    }
    await addReply(commentId, body);
    await refreshArtifact(artifact.artifact_id);
    setReplyDrafts((current) => ({ ...current, [commentId]: "" }));
  }

  async function handleReviewState(commentId: string, state: ReviewState) {
    if (artifact === null) {
      return;
    }
    await updateReviewState(commentId, state);
    await refreshArtifact(artifact.artifact_id);
  }

  async function handleSaveEdit(commentId: string) {
    if (artifact === null || !editingBody.trim()) {
      return;
    }
    await updateHumanComment(commentId, editingBody);
    await refreshArtifact(artifact.artifact_id);
    setEditingCommentId(null);
    setEditingBody("");
  }

  async function handleDeleteHumanComment(commentId: string) {
    if (artifact === null) {
      return;
    }
    await deleteHumanComment(commentId);
    await refreshArtifact(artifact.artifact_id);
    if (editingCommentId === commentId) {
      setEditingCommentId(null);
      setEditingBody("");
    }
  }

  function handleExport(format: "md" | "json") {
    if (artifact === null) {
      return;
    }
    window.open(getExportUrl(artifact.artifact_id, format), "_blank", "noopener,noreferrer");
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <ReviewHero overallScore={artifact?.summary?.overall_score ?? 0} verdict={artifact?.summary?.verdict ?? "No artifact loaded"} />

        <ReviewToolbar
          formState={formState}
          agents={agents}
          fileInputKey={fileInputKey}
          selectedFile={selectedFile}
          statusMessage={statusMessage}
          submitting={isSubmitting}
          importInputKey={importInputKey}
          onFormChange={(updater) =>
            setFormState((current) => {
              const next = updater(current);
              if (next.selectedAgents !== current.selectedAgents) {
                return {
                  ...next,
                  selectedAgents: resolveSelectedAgents(next.selectedAgents, agents),
                };
              }
              return next;
            })
          }
          onFileChange={(file) => {
            setSelectedFile(file);
            setFileInputKey((current) => current + 1);
            setFormState((current) => ({ ...current, sourceLabel: file?.name ?? "upload" }));
          }}
          onImportFileChange={handleImportFile}
          onSubmit={handleSubmit}
          onExport={handleExport}
        />

        {artifact?.error_message ? <section className={styles.errorBanner}>{artifact.error_message}</section> : null}

        <SelectionBanner
          selectionDraft={selectionDraft}
          commentDraft={commentDraft}
          onCommentDraftChange={setCommentDraft}
          onSave={handleCreateComment}
          onCancel={() => setSelectionDraft(null)}
        />

        <section className={styles.progressPanel}>
          <div className={styles.sectionTitle}>Run progress</div>
          <div className={styles.progressTrack} aria-hidden="true">
            <div className={styles.progressFill} style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
          <div className={styles.progressMeta}>
            <span>{Math.round(progress * 100)}% complete</span>
            <span>{artifact?.status ?? "idle"}</span>
          </div>
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

        <RunMetrics summary={artifact?.summary ?? null} />

        <section className={styles.workspace} ref={workspaceRef}>
          <DocumentPane
            document={artifact?.document ?? null}
            anchors={artifact?.anchors ?? []}
            threads={normalizedThreads}
            anchorThreadMap={anchorThreadMap}
            hoveredAnchorId={hoveredAnchorId}
            anchorRefs={anchorRefs}
            commentRefs={commentRefs}
            onHoverAnchor={setHoveredAnchorId}
            onSelectionDraft={setSelectionDraft}
            replyDrafts={replyDrafts}
            editingCommentId={editingCommentId}
            editingBody={editingBody}
            onReplyDraftChange={(commentId, value) => {
              setReplyDrafts((current) => ({ ...current, [commentId]: value }));
            }}
            onAddReply={handleReply}
            onReviewState={handleReviewState}
            onStartEditing={(commentId, body) => {
              setEditingCommentId(commentId);
              setEditingBody(body);
            }}
            onEditingBodyChange={setEditingBody}
            onSaveEdit={handleSaveEdit}
            onCancelEdit={() => {
              setEditingCommentId(null);
              setEditingBody("");
            }}
            onDeleteComment={handleDeleteHumanComment}
          />
          <CommentRail events={artifact?.events ?? []} />
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
