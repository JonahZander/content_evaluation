"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { CommentRail } from "@/components/review/CommentRail";
import { ConnectorCanvas } from "@/components/review/ConnectorCanvas";
import { DocumentPane } from "@/components/review/DocumentPane";
import { ReviewHero } from "@/components/review/ReviewHero";
import { RunMetrics } from "@/components/review/RunMetrics";
import { ReviewToolbar } from "@/components/review/ReviewToolbar";
import { SelectionBanner } from "@/components/review/SelectionBanner";
import { categoryColors } from "@/components/review/category-colors";
import {
  addReply,
  createComment,
  createRun,
  createRunFromFile,
  deleteHumanComment,
  fetchRun,
  getExportUrl,
  updateHumanComment,
  updateReviewState,
} from "@/lib/api";
import type { ReviewState, RunDetail } from "@/lib/types";

interface SelectionDraft {
  blockId: string;
  startOffset: number;
  endOffset: number;
  quote: string;
}

interface ReviewWorkbenchProps {
  initialRun: RunDetail;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function ReviewWorkbench({ initialRun }: ReviewWorkbenchProps) {
  const [runDetail, setRunDetail] = useState(initialRun);
  const [statusMessage, setStatusMessage] = useState("Using sample data until a run is submitted.");
  const [hoveredAnchorId, setHoveredAnchorId] = useState<string | null>(null);
  const [selectionDraft, setSelectionDraft] = useState<SelectionDraft | null>(null);
  const [commentDraft, setCommentDraft] = useState("");
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  const [editingBody, setEditingBody] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formState, setFormState] = useState({
    sourceType: "text" as "url" | "text" | "file",
    title: "",
    sourceLabel: "Manual input",
    text: initialRun.document?.text ?? "",
    url: "",
  });
  const [fileInputKey, setFileInputKey] = useState(0);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const anchorRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const commentRefs = useRef<Record<string, HTMLElement | null>>({});
  const [paths, setPaths] = useState<Array<{ id: string; path: string; color: string }>>([]);

  const threads = runDetail.threads ?? [];
  const anchorThreadMap = useMemo(() => {
    const map = new Map<string, { colors: string[] }>();
    threads.forEach((thread) => {
      map.set(thread.anchor.id, {
        colors: thread.comments.map((comment) => categoryColors[comment.category] ?? "var(--ink)"),
      });
    });
    return map;
  }, [threads]);

  async function refreshRun(runId: string) {
    const updated = await fetchRun(runId);
    setRunDetail(updated);
    setStatusMessage(`Run ${updated.run.status}`);
    return updated;
  }

  useEffect(() => {
    if (!activeRunId) {
      return;
    }

    const eventSource = new EventSource(`${API_BASE_URL}/api/v1/runs/${activeRunId}/events`);
    eventSource.onmessage = async () => {
      const updated = await refreshRun(activeRunId);
      if (updated.run.status === "completed" || updated.run.status === "failed") {
        setActiveRunId(null);
        eventSource.close();
      }
    };
    eventSource.onerror = () => {
      setStatusMessage("Live run updates disconnected. Refreshing on next action.");
      eventSource.close();
    };
    return () => eventSource.close();
  }, [activeRunId]);

  useEffect(() => {
    const updatePaths = () => {
      const container = workspaceRef.current;
      if (!container) {
        return;
      }
      const containerRect = container.getBoundingClientRect();
      const nextPaths = threads.flatMap((thread) => {
        const anchorElement = anchorRefs.current[thread.anchor.id];
        if (!anchorElement) {
          return [];
        }
        const anchorRect = anchorElement.getBoundingClientRect();
        const startX = anchorRect.right - containerRect.left;
        const startY = anchorRect.top - containerRect.top + anchorRect.height / 2;
        return thread.comments.flatMap((comment) => {
          const commentElement = commentRefs.current[comment.id];
          if (!commentElement) {
            return [];
          }
          const commentRect = commentElement.getBoundingClientRect();
          const endX = commentRect.left - containerRect.left;
          const endY = commentRect.top - containerRect.top + commentRect.height / 2;
          const controlOffset = Math.max(48, (endX - startX) / 2);
          return {
            id: comment.id,
            color: categoryColors[comment.category] ?? "var(--ink)",
            path: `M ${startX} ${startY} C ${startX + controlOffset} ${startY}, ${endX - controlOffset} ${endY}, ${endX} ${endY}`,
          };
        });
      });
      setPaths(nextPaths);
    };

    updatePaths();
    window.addEventListener("resize", updatePaths);
    return () => window.removeEventListener("resize", updatePaths);
  }, [threads, runDetail.document]);

  async function handleSubmit() {
    setStatusMessage("Submitting analysis run...");
    setIsSubmitting(true);
    try {
      const metadata =
        formState.sourceType === "file" && selectedFile
          ? await createRunFromFile(selectedFile)
          : await createRun({
              sourceType: formState.sourceType,
              sourceLabel:
                formState.sourceLabel || (formState.sourceType === "url" ? formState.url : "Manual input"),
              title: formState.title,
              text: formState.text,
              url: formState.url,
            });

      setActiveRunId(metadata.id);
      setStatusMessage(`Run ${metadata.id} queued`);
      await refreshRun(metadata.id);
      setSelectionDraft(null);
      setCommentDraft("");
      setEditingCommentId(null);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not submit run");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCreateComment() {
    if (!selectionDraft || !commentDraft.trim()) {
      return;
    }
    await createComment({
      runId: runDetail.run.id,
      body: commentDraft,
      blockId: selectionDraft.blockId,
      startOffset: selectionDraft.startOffset,
      endOffset: selectionDraft.endOffset,
      quote: selectionDraft.quote,
    });
    await refreshRun(runDetail.run.id);
    setSelectionDraft(null);
    setCommentDraft("");
  }

  async function handleReply(commentId: string) {
    const body = replyDrafts[commentId]?.trim();
    if (!body) {
      return;
    }
    await addReply(commentId, body);
    await refreshRun(runDetail.run.id);
    setReplyDrafts((current) => ({ ...current, [commentId]: "" }));
  }

  async function handleReviewState(commentId: string, state: ReviewState) {
    await updateReviewState(commentId, state);
    await refreshRun(runDetail.run.id);
  }

  async function handleSaveEdit(commentId: string) {
    if (!editingBody.trim()) {
      return;
    }
    await updateHumanComment(commentId, editingBody);
    await refreshRun(runDetail.run.id);
    setEditingCommentId(null);
    setEditingBody("");
  }

  async function handleDeleteHumanComment(commentId: string) {
    await deleteHumanComment(commentId);
    await refreshRun(runDetail.run.id);
    if (editingCommentId === commentId) {
      setEditingCommentId(null);
      setEditingBody("");
    }
  }

  function handleExport(format: "md" | "json") {
    window.open(getExportUrl(runDetail.run.id, format), "_blank", "noopener,noreferrer");
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <ReviewHero overallScore={runDetail.summary?.overall_score ?? 0} verdict={runDetail.summary?.verdict ?? "Waiting for analysis"} />

        <ReviewToolbar
          formState={formState}
          fileInputKey={fileInputKey}
          selectedFile={selectedFile}
          statusMessage={statusMessage}
          submitting={isSubmitting}
          onFormChange={setFormState}
          onFileChange={(file) => {
            setSelectedFile(file);
            setFileInputKey((current) => current + 1);
            setFormState((current) => ({ ...current, sourceLabel: file?.name ?? "upload" }));
          }}
          onSubmit={handleSubmit}
          onExport={handleExport}
        />

        {runDetail.run.error_message ? <section className={styles.errorBanner}>{runDetail.run.error_message}</section> : null}

        <SelectionBanner
          selectionDraft={selectionDraft}
          commentDraft={commentDraft}
          onCommentDraftChange={setCommentDraft}
          onSave={handleCreateComment}
          onCancel={() => setSelectionDraft(null)}
        />

        <RunMetrics summary={runDetail.summary} />

        <section className={styles.workspace} ref={workspaceRef}>
          <ConnectorCanvas paths={paths} />
          <DocumentPane
            document={runDetail.document}
            anchors={runDetail.anchors}
            anchorThreadMap={anchorThreadMap}
            hoveredAnchorId={hoveredAnchorId}
            anchorRefs={anchorRefs}
            onHoverAnchor={setHoveredAnchorId}
            onSelectionDraft={setSelectionDraft}
          />
          <CommentRail
            threads={threads}
            events={runDetail.events}
            hoveredAnchorId={hoveredAnchorId}
            commentRefs={commentRefs}
            replyDrafts={replyDrafts}
            editingCommentId={editingCommentId}
            editingBody={editingBody}
            onHoverAnchor={setHoveredAnchorId}
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
        </section>
      </div>
    </main>
  );
}
