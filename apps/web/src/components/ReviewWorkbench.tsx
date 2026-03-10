"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
import { RunDetail, ReviewState, TextAnchor } from "@/lib/types";
import styles from "@/components/ReviewWorkbench.module.css";

const categoryColors: Record<string, string> = {
  similarity: "var(--amber)",
  ai_likelihood: "var(--vermilion)",
  value: "var(--teal)",
  audience: "var(--cobalt)",
  editorial: "var(--olive)",
  synthesis: "var(--ink)",
  human: "var(--human)",
};

interface SelectionDraft {
  blockId: string;
  startOffset: number;
  endOffset: number;
  quote: string;
}

interface ReviewWorkbenchProps {
  initialRun: RunDetail;
}

export function ReviewWorkbench({ initialRun }: ReviewWorkbenchProps) {
  const [runDetail, setRunDetail] = useState(initialRun);
  const [statusMessage, setStatusMessage] = useState("Using sample data until a run is submitted.");
  const [hoveredAnchorId, setHoveredAnchorId] = useState<string | null>(null);
  const [selectionDraft, setSelectionDraft] = useState<SelectionDraft | null>(null);
  const [commentDraft, setCommentDraft] = useState("");
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
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
    const map = new Map<string, { colors: string[]; comments: typeof threads[number]["comments"] }>();
    threads.forEach((thread) => {
      map.set(thread.anchor.id, {
        colors: thread.comments.map((comment) => categoryColors[comment.category] ?? "var(--ink)"),
        comments: thread.comments,
      });
    });
    return map;
  }, [threads]);

  useEffect(() => {
    if (!activeRunId) {
      return;
    }

    const eventSource = new EventSource(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/runs/${activeRunId}/events`);
    eventSource.onmessage = async () => {
      const updated = await fetchRun(activeRunId);
      setRunDetail(updated);
      setStatusMessage(`Run ${updated.run.status}`);
      if (updated.run.status === "completed" || updated.run.status === "failed") {
        setActiveRunId(null);
        eventSource.close();
      }
    };
    eventSource.onerror = () => {
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

  const handleSubmit = async () => {
    setStatusMessage("Submitting analysis run...");
    try {
      const metadata =
        formState.sourceType === "file" && selectedFile
          ? await createRunFromFile(selectedFile)
          : await createRun({
              sourceType: formState.sourceType,
              sourceLabel: formState.sourceLabel || (formState.sourceType === "url" ? formState.url : "Manual input"),
              title: formState.title,
              text: formState.text,
              url: formState.url,
            });

      setActiveRunId(metadata.id);
      setStatusMessage(`Run ${metadata.id} queued`);
      const immediate = await fetchRun(metadata.id);
      setRunDetail(immediate);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Could not submit run");
    }
  };

  const handleCreateComment = async () => {
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
    const updated = await fetchRun(runDetail.run.id);
    setRunDetail(updated);
    setSelectionDraft(null);
    setCommentDraft("");
  };

  const handleTextSelection = (blockId: string, blockText: string) => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) {
      return;
    }
    const selectedText = selection.toString().trim();
    if (!selectedText) {
      return;
    }
    const startOffset = blockText.indexOf(selectedText);
    if (startOffset < 0) {
      return;
    }
    setSelectionDraft({
      blockId,
      startOffset,
      endOffset: startOffset + selectedText.length,
      quote: selectedText,
    });
  };

  const handleReply = async (commentId: string) => {
    const body = replyDrafts[commentId]?.trim();
    if (!body) {
      return;
    }
    await addReply(commentId, body);
    const updated = await fetchRun(runDetail.run.id);
    setRunDetail(updated);
    setReplyDrafts((current) => ({ ...current, [commentId]: "" }));
  };

  const handleReviewState = async (commentId: string, state: ReviewState) => {
    await updateReviewState(commentId, state);
    const updated = await fetchRun(runDetail.run.id);
    setRunDetail(updated);
  };

  const handleEditHumanComment = async (commentId: string, currentBody: string) => {
    const nextBody = window.prompt("Update comment", currentBody);
    if (!nextBody || nextBody === currentBody) {
      return;
    }
    await updateHumanComment(commentId, nextBody);
    setRunDetail(await fetchRun(runDetail.run.id));
  };

  const handleDeleteHumanComment = async (commentId: string) => {
    await deleteHumanComment(commentId);
    setRunDetail(await fetchRun(runDetail.run.id));
  };

  const openExport = (format: "md" | "json") => {
    window.open(getExportUrl(runDetail.run.id, format), "_blank", "noopener,noreferrer");
  };

  const renderBlock = (anchor: TextAnchor, blockText: string) => {
    const thread = anchorThreadMap.get(anchor.id);
    const colors = thread?.colors ?? ["rgba(0,0,0,0.08)"];
    const isHovered = hoveredAnchorId === anchor.id;
    const gradient =
      colors.length === 1
        ? `color-mix(in srgb, ${colors[0]} 18%, white)`
        : `linear-gradient(90deg, ${colors
            .map((color, index) => `${color} ${index * (100 / colors.length)}% ${(index + 1) * (100 / colors.length)}%`)
            .join(", ")})`;

    return (
      <span
        key={anchor.id}
        ref={(element) => {
          anchorRefs.current[anchor.id] = element;
        }}
        className={`${styles.anchorText} ${isHovered ? styles.anchorTextActive : ""}`}
        data-testid={`anchor-${anchor.id}`}
        onMouseEnter={() => setHoveredAnchorId(anchor.id)}
        onMouseLeave={() => setHoveredAnchorId(null)}
        style={{
          background: colors.length === 1 ? gradient : "rgba(255, 247, 236, 0.9)",
          boxShadow: colors.length > 1 ? `inset 0 0 0 1px rgba(0,0,0,0.04), inset 6px 0 0 0 ${colors[0]}` : undefined,
          borderBottom: `2px solid ${colors[0]}`,
        }}
      >
        {blockText.slice(anchor.start_offset, anchor.end_offset)}
      </span>
    );
  };

  const renderParagraph = (blockId: string, blockText: string) => {
    const anchors = runDetail.anchors
      .filter((anchor) => anchor.block_id === blockId)
      .sort((left, right) => left.start_offset - right.start_offset);

    if (anchors.length === 0) {
      return blockText;
    }

    const fragments: React.ReactNode[] = [];
    let cursor = 0;
    anchors.forEach((anchor) => {
      if (cursor < anchor.start_offset) {
        fragments.push(blockText.slice(cursor, anchor.start_offset));
      }
      fragments.push(renderBlock(anchor, blockText));
      cursor = anchor.end_offset;
    });
    if (cursor < blockText.length) {
      fragments.push(blockText.slice(cursor));
    }
    return fragments;
  };

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <section className={styles.hero}>
          <div className={styles.eyebrow}>Content Evaluation Workbench</div>
          <div className={styles.titleRow}>
            <div>
              <h1 className={styles.heroTitle}>Read the draft. Trace every agent judgment. Reply where it matters.</h1>
              <p className={styles.heroCopy}>
                The document stays on the left, the comment threads stay on the right, and every judgment remains tied to
                highlighted text. Export the full analysis as Markdown or JSON when the review is done.
              </p>
            </div>
            <aside className={styles.scorePanel}>
              <span className={styles.scoreLabel}>Overall evaluation</span>
              <strong className={styles.scoreValue}>{runDetail.summary?.overall_score ?? 0}</strong>
              <p className={styles.scoreCaption}>{runDetail.summary?.verdict ?? "Waiting for analysis"}</p>
            </aside>
          </div>
        </section>

        <section className={styles.toolbar}>
          <div className={styles.toolbarGroup}>
            <select
              className={styles.toolbarSelect}
              value={formState.sourceType}
              onChange={(event) =>
                setFormState((current) => ({ ...current, sourceType: event.target.value as "url" | "text" | "file" }))
              }
            >
              <option value="text">Pasted text</option>
              <option value="url">URL</option>
              <option value="file">Text file</option>
            </select>
            <input
              className={styles.toolbarInput}
              value={formState.title}
              onChange={(event) => setFormState((current) => ({ ...current, title: event.target.value }))}
              placeholder="Draft title"
            />
            {formState.sourceType === "url" ? (
              <input
                className={styles.toolbarInput}
                value={formState.url}
                onChange={(event) => setFormState((current) => ({ ...current, url: event.target.value, sourceLabel: event.target.value }))}
                placeholder="https://example.com/post"
              />
            ) : null}
            {formState.sourceType === "file" ? (
              <input
                key={fileInputKey}
                className={styles.toolbarInput}
                type="file"
                accept=".txt,.md,text/plain,text/markdown"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  setSelectedFile(file);
                  setFormState((current) => ({ ...current, sourceLabel: file?.name ?? "upload" }));
                }}
              />
            ) : (
              <textarea
                className={styles.toolbarTextarea}
                value={formState.text}
                onChange={(event) => setFormState((current) => ({ ...current, text: event.target.value }))}
                placeholder="Paste draft text"
              />
            )}
          </div>
          <div className={styles.toolbarGroup}>
            <button className={styles.button} onClick={handleSubmit}>
              Analyze content
            </button>
            <button className={styles.ghostButton} onClick={() => openExport("md")}>
              Export Markdown
            </button>
            <button className={styles.ghostButton} onClick={() => openExport("json")}>
              Export JSON
            </button>
            <span className={styles.statusPill}>{statusMessage}</span>
          </div>
        </section>

        {selectionDraft ? (
          <section className={styles.selectionBanner}>
            <strong>Create a reviewer comment</strong>
            <p className={styles.selectionQuote}>“{selectionDraft.quote}”</p>
            <div className={styles.replyComposer}>
              <textarea
                className={styles.toolbarTextarea}
                value={commentDraft}
                onChange={(event) => setCommentDraft(event.target.value)}
                placeholder="Add a reviewer note for this selection"
              />
              <div className={styles.toolbarGroup}>
                <button className={styles.button} onClick={handleCreateComment}>
                  Save comment
                </button>
                <button className={styles.ghostButton} onClick={() => setSelectionDraft(null)}>
                  Cancel
                </button>
              </div>
            </div>
          </section>
        ) : null}

        <section className={styles.metrics}>
          <article className={styles.metricCard}>
            <div className={styles.metricLabel}>Novelty</div>
            <div className={styles.metricValue}>{Math.round((runDetail.summary?.novelty_score ?? 0) * 100)}%</div>
          </article>
          <article className={styles.metricCard}>
            <div className={styles.metricLabel}>AI likelihood</div>
            <div className={styles.metricValue}>{Math.round((runDetail.summary?.ai_likelihood ?? 0) * 100)}%</div>
          </article>
          <article className={styles.metricCard}>
            <div className={styles.metricLabel}>Value</div>
            <div className={styles.metricValue}>{runDetail.summary?.value_summary ?? "Pending"}</div>
          </article>
          <article className={styles.metricCard}>
            <div className={styles.metricLabel}>Audience</div>
            <div className={styles.metricValue}>{runDetail.summary?.audience_summary ?? "Pending"}</div>
          </article>
        </section>

        <section className={styles.workspace} ref={workspaceRef}>
          <svg className={styles.connectorCanvas} data-testid="connector-canvas" aria-hidden="true">
            {paths.map((item) => (
              <path
                key={item.id}
                data-testid={`connector-${item.id}`}
                d={item.path}
                fill="none"
                stroke={item.color}
                strokeWidth="2.5"
                strokeOpacity="0.7"
                strokeLinecap="round"
              />
            ))}
          </svg>
          <div className={styles.documentPane}>
            <div className={styles.sectionTitle}>Text under review</div>
            <h2 className={styles.documentTitle}>{runDetail.document?.title ?? "No document loaded"}</h2>
            {runDetail.document?.blocks.map((block) => (
              <p
                key={block.id}
                className={styles.paragraph}
                data-block-id={block.id}
                onMouseUp={() => handleTextSelection(block.id, block.text)}
              >
                {renderParagraph(block.id, block.text)}
              </p>
            ))}
          </div>

          <aside className={styles.commentPane}>
            <div className={styles.sectionTitle}>Comment rail</div>
            {threads.map((thread) => (
              <section
                key={thread.anchor.id}
                className={styles.thread}
                data-testid={`thread-${thread.anchor.id}`}
                onMouseEnter={() => setHoveredAnchorId(thread.anchor.id)}
                onMouseLeave={() => setHoveredAnchorId(null)}
              >
                <div className={styles.threadHeader}>
                  <strong>Linked section</strong>
                  <span className={styles.threadQuote}>{thread.anchor.quote}</span>
                </div>
                <div className={styles.threadCards}>
                  {thread.comments.map((comment) => (
                    <article
                      key={comment.id}
                      ref={(element) => {
                        commentRefs.current[comment.id] = element;
                      }}
                      className={styles.card}
                      data-testid={`comment-${comment.id}`}
                    >
                      <div className={styles.cardHeader}>
                        <span className={styles.pill} style={{ color: categoryColors[comment.category] ?? "var(--ink)" }}>
                          {comment.author_label}
                        </span>
                        <span className={styles.pill}>{comment.category.replace("_", " ")}</span>
                        <span className={styles.reviewBadge}>{comment.review_state}</span>
                      </div>
                      <p className={styles.cardBody}>{comment.body}</p>
                      {comment.suggestion ? <div className={styles.suggestion}>Suggestion: {comment.suggestion}</div> : null}
                      {comment.author_type === "agent" ? (
                        <div className={styles.toolbarGroup}>
                          {(["accepted", "rejected", "uncertain"] as ReviewState[]).map((state) => (
                            <button
                              key={state}
                              className={`${styles.stateButton} ${
                                comment.review_state === state ? styles.stateButtonActive : ""
                              }`}
                              onClick={() => handleReviewState(comment.id, state)}
                            >
                              {state}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className={styles.toolbarGroup}>
                          <button className={styles.ghostButton} onClick={() => handleEditHumanComment(comment.id, comment.body)}>
                            Edit
                          </button>
                          <button className={styles.ghostButton} onClick={() => handleDeleteHumanComment(comment.id)}>
                            Delete
                          </button>
                        </div>
                      )}

                      <div className={styles.replyList}>
                        {comment.replies.map((reply) => (
                          <div key={reply.id} className={styles.reply}>
                            <span className={styles.replyMeta}>{reply.author_label}</span>
                            <div>{reply.body}</div>
                          </div>
                        ))}
                      </div>

                      <div className={styles.replyComposer}>
                        <textarea
                          className={styles.replyInput}
                          value={replyDrafts[comment.id] ?? ""}
                          onChange={(event) => setReplyDrafts((current) => ({ ...current, [comment.id]: event.target.value }))}
                          placeholder="Reply to this comment"
                        />
                        <button className={styles.button} onClick={() => handleReply(comment.id)}>
                          Add reply
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}

            <section className={styles.eventPanel}>
              <div className={styles.sectionTitle}>Run log</div>
              {runDetail.events.map((event) => (
                <div key={event.id} className={styles.eventItem}>
                  <div>
                    <strong>{event.stage}</strong>
                    <div>{event.message}</div>
                  </div>
                  <div className={styles.eventMeta}>
                    {event.agent_name ?? "system"}
                    <br />
                    {event.model_name ?? "n/a"}
                  </div>
                </div>
              ))}
            </section>
          </aside>
        </section>
      </div>
    </main>
  );
}
