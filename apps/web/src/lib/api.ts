import {
  AgentCatalogEntry,
  AnalysisArtifact,
  ArtifactDocument,
  PersistenceMode,
  RevisedMarkdownDiffDecision,
  ReviewState,
} from "@/lib/types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface CreateRunPayload {
  sourceType: "url" | "text" | "file";
  sourceLabel: string;
  title?: string;
  text?: string;
  url?: string;
  selectedAgents: string[];
  persistenceMode: PersistenceMode;
  includeDebugTrace: boolean;
}

export interface CreateCommentPayload {
  artifactId: string;
  body: string;
  anchorId?: string;
  blockId?: string;
  startOffset?: number;
  endOffset?: number;
  quote?: string;
}

export interface AppendAgentsPayload {
  artifactId: string;
  selectedAgents: string[];
}

export interface UpdateRevisedMarkdownDiffReviewDecision {
  diffId: string;
  decision: RevisedMarkdownDiffDecision;
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : undefined;
    } catch {
      // body is not JSON
    }
    throw new Error(detail ?? `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

async function assertOk(response: Response): Promise<void> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : undefined;
    } catch {
      // body is not JSON
    }
    throw new Error(detail ?? `Request failed with status ${response.status}`);
  }
}

export async function fetchAgents(): Promise<AgentCatalogEntry[]> {
  return parseJson(await fetch(`${API_BASE_URL}/api/v1/agents`));
}

export async function createRun(payload: CreateRunPayload, signal?: AbortSignal): Promise<AnalysisArtifact> {
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
        selected_agents: payload.selectedAgents,
        persistence_mode: payload.persistenceMode,
        include_debug_trace: payload.includeDebugTrace,
      }),
      signal,
    }),
  );
}

export async function previewSource(payload: Omit<CreateRunPayload, "selectedAgents" | "persistenceMode" | "includeDebugTrace">, signal?: AbortSignal): Promise<ArtifactDocument> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/sources/preview`, {
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
      signal,
    }),
  );
}

export async function createRunFromFile(
  file: File,
  options: Pick<CreateRunPayload, "selectedAgents" | "persistenceMode" | "includeDebugTrace">,
  signal?: AbortSignal,
): Promise<AnalysisArtifact> {
  const formData = new FormData();
  formData.append("file", file);
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs?selected_agents=${options.selectedAgents.join(",")}`, {
      method: "POST",
      body: formData,
      headers: {
        "X-Artifact-Persistence-Mode": options.persistenceMode,
        "X-Artifact-Debug-Trace": String(options.includeDebugTrace),
      },
      signal,
    }),
  );
}

export async function fetchArtifact(artifactId: string): Promise<AnalysisArtifact> {
  return parseJson(await fetch(`${API_BASE_URL}/api/v1/runs/${artifactId}`));
}

export async function appendAgents(payload: AppendAgentsPayload): Promise<AnalysisArtifact> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs/${payload.artifactId}/agents`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        selected_agents: payload.selectedAgents,
      }),
    }),
  );
}

export async function cancelRun(artifactId: string): Promise<AnalysisArtifact> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs/${artifactId}/cancel`, {
      method: "POST",
    }),
  );
}

export async function generateRevisedMarkdown(artifactId: string): Promise<AnalysisArtifact> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs/${artifactId}/revised-markdown`, {
      method: "POST",
    }),
  );
}

export async function updateRevisedMarkdownDiffReview(
  artifactId: string,
  decisions: UpdateRevisedMarkdownDiffReviewDecision[],
): Promise<AnalysisArtifact> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs/${artifactId}/revised-markdown/diff-review`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        decisions: decisions.map((item) => ({
          diff_id: item.diffId,
          decision: item.decision,
        })),
      }),
    }),
  );
}

export async function applyRevisedMarkdown(artifactId: string): Promise<AnalysisArtifact> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/runs/${artifactId}/revised-markdown/apply`, {
      method: "POST",
    }),
  );
}

export async function importArtifact(artifact: AnalysisArtifact): Promise<AnalysisArtifact> {
  return parseJson(
    await fetch(`${API_BASE_URL}/api/v1/artifacts/import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ artifact }),
    }),
  );
}

export async function createComment(payload: CreateCommentPayload): Promise<void> {
  await parseJson(
    await fetch(`${API_BASE_URL}/api/v1/comments`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        artifact_id: payload.artifactId,
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

export async function deleteReply(replyId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/replies/${replyId}`, {
    method: "DELETE",
  });
  await assertOk(response);
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
  await assertOk(response);
}

export function getExportUrl(artifactId: string, format: "md" | "json" | "todo"): string {
  if (format === "todo") {
    return `${API_BASE_URL}/api/v1/runs/${artifactId}/export.todo.md`;
  }
  return `${API_BASE_URL}/api/v1/runs/${artifactId}/export.${format}`;
}
