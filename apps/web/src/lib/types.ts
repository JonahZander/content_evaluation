export type SourceType = "url" | "text" | "file" | "artifact";
export type ContentFormat = "plain_text" | "markdown";
export type RunStatus = "draft" | "queued" | "running" | "completed" | "failed" | "canceled";
export type ReviewState = "unreviewed" | "accepted" | "rejected" | "uncertain";
export type AuthorType = "agent" | "human";
export type AgentCategory = "fact_check" | "similarity" | "ai_likelihood" | "value" | "audience" | "editorial" | "synthesis" | "research" | "human";
export type RuntimeMode = "mock" | "live";
export type PersistenceMode = "session" | "workspace";
export type AgentPlanStatus = "pending" | "queued" | "running" | "completed" | "failed" | "skipped";
export type AgentExecutionMode = "single_turn" | "multi_step";
export type ProviderKind = "deep_research" | "search" | "analysis" | "extract";
export type EventType = "run" | "artifact" | "agent";
export type ArtifactBlockKind = "paragraph" | "heading" | "code";
export type ArtifactBlockOrigin = "source" | "synthetic_unmatched";
export type ArtifactInlineMarkKind = "strong" | "emphasis" | "code" | "link";
export type ArtifactAnchorMatchKind = "source" | "synthetic_unmatched";
export type RevisionMode = "surgical" | "rewrite";

export interface ArtifactSource {
  source_type: SourceType;
  source_label: string;
  title?: string | null;
  url?: string | null;
  imported: boolean;
}

export interface ArtifactBlock {
  id: string;
  index: number;
  text: string;
  kind?: ArtifactBlockKind;
  origin?: ArtifactBlockOrigin;
  markdown?: string | null;
  level?: number | null;
  language?: string | null;
  marks?: ArtifactInlineMark[];
}

export interface ArtifactInlineMark {
  start_offset: number;
  end_offset: number;
  kind: ArtifactInlineMarkKind;
  href?: string | null;
}

export interface ArtifactDocument {
  id: string;
  revision_id: string;
  title: string;
  source_type: SourceType;
  source_label: string;
  content_format?: ContentFormat;
  raw_content?: string;
  text: string;
  blocks: ArtifactBlock[];
}

export interface ArtifactAnchorSegment {
  block_id: string;
  start_offset: number;
  end_offset: number;
}

export interface ArtifactAnchor {
  id: string;
  document_revision_id?: string | null;
  block_id: string;
  start_offset: number;
  end_offset: number;
  quote: string;
  match_kind?: ArtifactAnchorMatchKind;
  segments?: ArtifactAnchorSegment[];
}

export interface ArtifactReply {
  id: string;
  comment_id: string;
  author_type: AuthorType;
  author_label: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface ArtifactComment {
  id: string;
  artifact_id: string;
  anchor_id: string;
  document_revision_id?: string | null;
  author_type: AuthorType;
  author_label: string;
  category: AgentCategory;
  body: string;
  suggestion?: string | null;
  sources?: string[];
  metadata?: Record<string, unknown>;
  review_state: ReviewState;
  created_at: string;
  updated_at: string;
  replies: ArtifactReply[];
}

export interface ArtifactThread {
  document_revision_id?: string | null;
  anchor: ArtifactAnchor;
  comments: ArtifactComment[];
}

export interface AgentFinding {
  id: string;
  document_revision_id?: string | null;
  category: AgentCategory;
  agent_name: string;
  anchor_ids: string[];
  rationale: string;
  confidence: number;
  model_name: string;
  suggestion?: string | null;
  sources?: string[];
  metadata: Record<string, unknown>;
}

export interface ArtifactAgentPlanItem {
  agent_id: string;
  display_name: string;
  category: AgentCategory;
  depends_on: string[];
  provider_kind: ProviderKind;
  execution_mode: AgentExecutionMode;
  instruction_file: string;
  status: AgentPlanStatus;
  model_name?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  message?: string | null;
}

export interface ArtifactAgentResult {
  agent_id: string;
  document_revision_id?: string | null;
  category: AgentCategory;
  status: AgentPlanStatus;
  findings: AgentFinding[];
  summary?: string | null;
  raw_output: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface ArtifactStructuralCompleteness {
  has_intro: boolean;
  has_headings: boolean;
  has_conclusion: boolean;
}

export interface ArtifactClaimSummary {
  claim_text: string;
  verdict: string;
  evidence_summary: string;
  source_links: string[];
  anchor_quote?: string;
  value_add?: string;
  official_source_links?: string[];
  related_post_links?: string[];
}

export interface ArtifactSummary {
  overall_score: number;
  verdict: string;
  value_summary: string;
  audience_summary: string;
  novelty_score: number;
  ai_likelihood: number;
  tl_dr?: string;
  word_count?: number;
  estimated_reading_time_minutes?: number;
}

export interface ArtifactOverlapItem {
  title: string;
  url: string;
  note: string;
}

export interface ArtifactReviewSummary {
  content_summary: string;
  research_summary: string;
  inferred_audience: string;
  overlap_items: ArtifactOverlapItem[];
  tl_dr?: string;
  word_count?: number;
  estimated_reading_time_minutes?: number;
  article_format?: string;
  reading_difficulty?: string;
  structural_completeness?: ArtifactStructuralCompleteness;
  main_claims?: ArtifactClaimSummary[];
}

export type RevisedMarkdownDiffDecision = "pending" | "accepted" | "rejected";

export interface ArtifactRevisedDocument {
  mode: RevisionMode;
  source_revision_id: string;
  direction_prompt?: string | null;
  markdown: string;
  accepted_comment_ids: string[];
  generated_at: string;
}

export interface ArtifactDiffItem {
  id: string;
  change_type: string;
  original_start_line: number;
  original_end_line: number;
  candidate_start_line: number;
  candidate_end_line: number;
  before_text: string;
  after_text: string;
  decision: RevisedMarkdownDiffDecision;
}

export interface ArtifactDiffReview {
  mode: RevisionMode;
  source_revision_id: string;
  direction_prompt?: string | null;
  original_markdown: string;
  candidate_markdown: string;
  diff_items: ArtifactDiffItem[];
}

export interface ArtifactPreviousDraftSnapshot {
  document_revision_id: string;
  document: ArtifactDocument;
  anchors: ArtifactAnchor[];
  threads: ArtifactThread[];
  agent_results: ArtifactAgentResult[];
  archived_at: string;
}

export interface ArtifactEvent {
  id: string;
  artifact_id: string;
  event_type: EventType;
  stage: string;
  message: string;
  status: string;
  progress?: number | null;
  agent_id?: string | null;
  agent_name?: string | null;
  model_name?: string | null;
  attempt?: number | null;
  max_attempts?: number | null;
  error_kind?: string | null;
  provider_name?: string | null;
  snapshot_available: boolean;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface ArtifactDebug {
  traces: Array<Record<string, unknown>>;
}

export interface RunConfig {
  selected_agents: string[];
  resolved_agents: string[];
  runtime_mode: RuntimeMode;
  persistence_mode: PersistenceMode;
  include_debug_trace: boolean;
}

export interface AnalysisArtifact {
  schema_version: string;
  artifact_id: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  source: ArtifactSource;
  document: ArtifactDocument | null;
  run_config: RunConfig;
  agent_plan: ArtifactAgentPlanItem[];
  agent_results: ArtifactAgentResult[];
  anchors: ArtifactAnchor[];
  threads: ArtifactThread[];
  summary: ArtifactSummary | null;
  review_summary?: ArtifactReviewSummary | null;
  revised_document?: ArtifactRevisedDocument | null;
  diff_review?: ArtifactDiffReview | null;
  previous_draft_snapshot?: ArtifactPreviousDraftSnapshot | null;
  events: ArtifactEvent[];
  debug?: ArtifactDebug | null;
  error_message?: string | null;
}

export interface AgentCatalogEntry {
  agent_id: string;
  display_name: string;
  category: AgentCategory;
  depends_on: string[];
  execution_mode: AgentExecutionMode;
  provider_kind: ProviderKind;
  description: string;
  default_enabled: boolean;
}

export interface SelectionDraft {
  blockId: string;
  startOffset: number;
  endOffset: number;
  quote: string;
}

export function anchorSegments(anchor: ArtifactAnchor): ArtifactAnchorSegment[] {
  if (anchor.segments?.length) {
    return anchor.segments;
  }
  return [
    {
      block_id: anchor.block_id,
      start_offset: anchor.start_offset,
      end_offset: anchor.end_offset,
    },
  ];
}

export function anchorPrimarySegment(anchor: ArtifactAnchor): ArtifactAnchorSegment {
  return anchorSegments(anchor)[0];
}
