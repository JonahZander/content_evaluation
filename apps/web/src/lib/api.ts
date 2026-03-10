import { RunDetail, RunMetadata, ReviewState } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface CreateRunPayload {
  sourceType: "url" | "text" | "file";
  sourceLabel: string;
  title?: string;
  text?: string;
  url?: string;
}

export interface CreateCommentPayload {
  runId: string;
  body: string;
  anchorId?: string;
  blockId?: string;
  startOffset?: number;
  endOffset?: number;
  quote?: string;
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function createRun(payload: CreateRunPayload): Promise<RunMetadata> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        source_type: payload.sourceType,
        source_label: payload.sourceLabel,
        title: payload.title,
        text: payload.text,
        url: payload.url,
      }),
    }),
  );
}

export async function createRunFromFile(file: File): Promise<RunMetadata> {
  const formData = new FormData();
  formData.append("file", file);
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs`, {
      method: "POST",
      body: formData,
    }),
  );
}

export async function fetchRun(runId: string): Promise<RunDetail> {
  return parseJson(await fetch(`${API_BASE_URL}/api/v1/runs/${runId}`));
}

export async function createComment(payload: CreateCommentPayload): Promise<void> {
  await parseJson(
    await fetch(`${API_BASE_URL}/api/v1/comments`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        run_id: payload.runId,
        body: payload.body,
        anchor_id: payload.anchorId,
        block_id: payload.blockId,
        start_offset: payload.startOffset,
        end_offset: payload.endOffset,
        quote: payload.quote,
      }),
    }),
  );
}

export async function addReply(commentId: string, body: string): Promise<void> {
  await parseJson(
    await fetch(`${API_BASE_URL}/api/v1/comments/${commentId}/replies`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ body }),
    }),
  );
}

export async function updateReviewState(commentId: string, state: ReviewState): Promise<void> {
  await parseJson(
    await fetch(`${API_BASE_URL}/api/v1/comments/${commentId}/review-state`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ review_state: state }),
    }),
  );
}

export async function updateHumanComment(commentId: string, body: string): Promise<void> {
  await parseJson(
    await fetch(`${API_BASE_URL}/api/v1/comments/${commentId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ body }),
    }),
  );
}

export async function deleteHumanComment(commentId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/comments/${commentId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
}

export function getExportUrl(runId: string, format: "md" | "json"): string {
  return `${API_BASE_URL}/api/v1/runs/${runId}/export.${format}`;
}
