export type SourceType = "url" | "text" | "file";
export type RunStatus = "queued" | "running" | "completed" | "failed";
export type ReviewState = "unreviewed" | "accepted" | "rejected" | "uncertain";
export type AuthorType = "agent" | "human";
export type AgentCategory = "similarity" | "ai_likelihood" | "value" | "audience" | "editorial" | "synthesis" | "human";

export interface RunMetadata {
  id: string;
  status: RunStatus;
  source_type: SourceType;
  source_label: string;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
}

export interface DocumentBlock {
  id: string;
  index: number;
  text: string;
}

export interface NormalizedDocument {
  id: string;
  title: string;
  source_type: SourceType;
  source_label: string;
  text: string;
  blocks: DocumentBlock[];
}

export interface TextAnchor {
  id: string;
  block_id: string;
  start_offset: number;
  end_offset: number;
  quote: string;
}

export interface CommentReply {
  id: string;
  comment_id: string;
  author_type: AuthorType;
  author_label: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface Comment {
  id: string;
  run_id: string;
  anchor_id: string;
  author_type: AuthorType;
  author_label: string;
  category: AgentCategory;
  body: string;
  suggestion?: string | null;
  review_state: ReviewState;
  created_at: string;
  updated_at: string;
  replies: CommentReply[];
}

export interface CommentThread {
  anchor: TextAnchor;
  comments: Comment[];
}

export interface AgentFinding {
  id: string;
  category: AgentCategory;
  agent_name: string;
  anchor_ids: string[];
  rationale: string;
  confidence: number;
  model_name: string;
  suggestion?: string | null;
  metadata: Record<string, unknown>;
}

export interface RunSummary {
  overall_score: number;
  verdict: string;
  value_summary: string;
  audience_summary: string;
  novelty_score: number;
  ai_likelihood: number;
}

export interface RunEvent {
  id: string;
  run_id: string;
  stage: string;
  message: string;
  status: string;
  agent_name?: string | null;
  model_name?: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface RunDetail {
  run: RunMetadata;
  document: NormalizedDocument | null;
  anchors: TextAnchor[];
  threads: CommentThread[];
  findings: AgentFinding[];
  summary: RunSummary | null;
  events: RunEvent[];
}
