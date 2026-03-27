import type { ReviewFormState } from "@/components/review/ReviewToolbar";
import type {
  AgentCatalogEntry,
  AnalysisArtifact,
  ArtifactDocument,
  ReviewState,
  SelectionDraft,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export interface WorkbenchState {
  // Session
  artifact: AnalysisArtifact | null;
  previewDocument: ArtifactDocument | null;
  activeArtifactId: string | null;
  statusMessage: string;
  agents: AgentCatalogEntry[];

  // Submission
  isSubmitting: boolean;
  isPreviewing: boolean;
  isGeneratingRevision: boolean;
  isSavingDiffReview: boolean;
  isApplyingRevision: boolean;
  showTextPreview: boolean;
  formState: ReviewFormState;
  hiddenPreviewBlockIds: string[];
  selectedFile: File | null;
  fileInputKey: number;
  importInputKey: number;

  // Comment editing
  selectionDraft: SelectionDraft | null;
  commentDraft: string;
  replyDrafts: Record<string, string>;
  activeReplyComposerId: string | null;
  editingCommentId: string | null;
  editingBody: string;
  hoveredAnchorId: string | null;

  // Export
  hasDownloadedJson: boolean;
}

export const DEFAULT_FORM_STATE: ReviewFormState = {
  sourceType: "text",
  title: "",
  sourceLabel: "Manual input",
  text: "",
  url: "",
  persistenceMode: "workspace",
  includeDebugTrace: true,
  selectedAgents: [],
};

export const initialWorkbenchState: WorkbenchState = {
  artifact: null,
  previewDocument: null,
  activeArtifactId: null,
  statusMessage: "",
  agents: [],

  isSubmitting: false,
  isPreviewing: false,
  isGeneratingRevision: false,
  isSavingDiffReview: false,
  isApplyingRevision: false,
  showTextPreview: false,
  formState: DEFAULT_FORM_STATE,
  hiddenPreviewBlockIds: [],
  selectedFile: null,
  fileInputKey: 0,
  importInputKey: 0,

  selectionDraft: null,
  commentDraft: "",
  replyDrafts: {},
  activeReplyComposerId: null,
  editingCommentId: null,
  editingBody: "",
  hoveredAnchorId: null,

  hasDownloadedJson: false,
};

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export type WorkbenchAction =
  | { type: "SET_ARTIFACT"; artifact: AnalysisArtifact | null }
  | { type: "SET_PREVIEW_DOCUMENT"; document: ArtifactDocument | null }
  | { type: "SET_ACTIVE_ARTIFACT_ID"; id: string | null }
  | { type: "SET_STATUS_MESSAGE"; message: string }
  | { type: "SET_AGENTS"; agents: AgentCatalogEntry[] }
  | { type: "SET_IS_SUBMITTING"; value: boolean }
  | { type: "SET_IS_PREVIEWING"; value: boolean }
  | { type: "SET_IS_GENERATING_REVISION"; value: boolean }
  | { type: "SET_IS_SAVING_DIFF_REVIEW"; value: boolean }
  | { type: "SET_IS_APPLYING_REVISION"; value: boolean }
  | { type: "TOGGLE_TEXT_PREVIEW" }
  | { type: "SET_FORM_STATE"; formState: ReviewFormState }
  | { type: "UPDATE_FORM_STATE"; updater: (current: ReviewFormState) => ReviewFormState }
  | { type: "HIDE_PREVIEW_BLOCK"; blockId: string }
  | { type: "RESTORE_PREVIEW_BLOCK"; blockId: string }
  | { type: "RESTORE_ALL_PREVIEW_BLOCKS" }
  | { type: "SET_SELECTED_FILE"; file: File | null }
  | { type: "BUMP_FILE_INPUT_KEY" }
  | { type: "BUMP_IMPORT_INPUT_KEY" }
  | { type: "SET_SELECTION_DRAFT"; draft: SelectionDraft | null }
  | { type: "SET_COMMENT_DRAFT"; draft: string }
  | { type: "SET_REPLY_DRAFT"; commentId: string; body: string }
  | { type: "SET_ACTIVE_REPLY_COMPOSER"; commentId: string | null }
  | { type: "SET_EDITING_COMMENT"; commentId: string | null; body: string }
  | { type: "SET_EDITING_BODY"; body: string }
  | { type: "SET_HOVERED_ANCHOR_ID"; anchorId: string | null }
  | { type: "SET_HAS_DOWNLOADED_JSON"; value: boolean }
  | { type: "CLEAR_ANALYSIS_STATE"; resetForm: boolean; currentAgents: AgentCatalogEntry[] }
  | {
      type: "RESTORE_STORED_STATE";
      artifact: AnalysisArtifact | null;
      previewDocument: ArtifactDocument | null;
      formState: ReviewFormState;
      hasDownloadedJson: boolean;
      activeArtifactId: string | null;
      statusMessage: string;
    };

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

export function workbenchReducer(state: WorkbenchState, action: WorkbenchAction): WorkbenchState {
  switch (action.type) {
    case "SET_ARTIFACT":
      return { ...state, artifact: action.artifact, showTextPreview: false };
    case "SET_PREVIEW_DOCUMENT":
      return { ...state, previewDocument: action.document, hiddenPreviewBlockIds: [], showTextPreview: false };
    case "SET_ACTIVE_ARTIFACT_ID":
      return { ...state, activeArtifactId: action.id };
    case "SET_STATUS_MESSAGE":
      return { ...state, statusMessage: action.message };
    case "SET_AGENTS":
      return { ...state, agents: action.agents };
    case "SET_IS_SUBMITTING":
      return { ...state, isSubmitting: action.value };
    case "SET_IS_PREVIEWING":
      return { ...state, isPreviewing: action.value };
    case "SET_IS_GENERATING_REVISION":
      return { ...state, isGeneratingRevision: action.value };
    case "SET_IS_SAVING_DIFF_REVIEW":
      return { ...state, isSavingDiffReview: action.value };
    case "SET_IS_APPLYING_REVISION":
      return { ...state, isApplyingRevision: action.value };
    case "TOGGLE_TEXT_PREVIEW":
      return { ...state, showTextPreview: !state.showTextPreview };
    case "SET_FORM_STATE":
      return { ...state, formState: action.formState };
    case "UPDATE_FORM_STATE":
      return { ...state, formState: action.updater(state.formState) };
    case "HIDE_PREVIEW_BLOCK":
      return state.hiddenPreviewBlockIds.includes(action.blockId)
        ? state
        : { ...state, hiddenPreviewBlockIds: [...state.hiddenPreviewBlockIds, action.blockId] };
    case "RESTORE_PREVIEW_BLOCK":
      return {
        ...state,
        hiddenPreviewBlockIds: state.hiddenPreviewBlockIds.filter((blockId) => blockId !== action.blockId),
      };
    case "RESTORE_ALL_PREVIEW_BLOCKS":
      return { ...state, hiddenPreviewBlockIds: [] };
    case "SET_SELECTED_FILE":
      return { ...state, selectedFile: action.file };
    case "BUMP_FILE_INPUT_KEY":
      return { ...state, fileInputKey: state.fileInputKey + 1 };
    case "BUMP_IMPORT_INPUT_KEY":
      return { ...state, importInputKey: state.importInputKey + 1 };
    case "SET_SELECTION_DRAFT":
      return { ...state, selectionDraft: action.draft };
    case "SET_COMMENT_DRAFT":
      return { ...state, commentDraft: action.draft };
    case "SET_REPLY_DRAFT":
      return { ...state, replyDrafts: { ...state.replyDrafts, [action.commentId]: action.body } };
    case "SET_ACTIVE_REPLY_COMPOSER":
      return { ...state, activeReplyComposerId: action.commentId };
    case "SET_EDITING_COMMENT":
      return { ...state, editingCommentId: action.commentId, editingBody: action.body };
    case "SET_EDITING_BODY":
      return { ...state, editingBody: action.body };
    case "SET_HOVERED_ANCHOR_ID":
      return { ...state, hoveredAnchorId: action.anchorId };
    case "SET_HAS_DOWNLOADED_JSON":
      return { ...state, hasDownloadedJson: action.value };
    case "CLEAR_ANALYSIS_STATE": {
      const resetFormState = action.resetForm
        ? {
            ...DEFAULT_FORM_STATE,
            selectedAgents: state.formState.selectedAgents,
            persistenceMode: state.formState.persistenceMode,
            includeDebugTrace: state.formState.includeDebugTrace,
          }
        : state.formState;
      return {
        ...state,
        artifact: null,
        previewDocument: null,
        activeArtifactId: null,
        isSubmitting: false,
        isPreviewing: false,
        isGeneratingRevision: false,
        isSavingDiffReview: false,
        isApplyingRevision: false,
        showTextPreview: false,
        selectionDraft: null,
        commentDraft: "",
        replyDrafts: {},
        activeReplyComposerId: null,
        editingCommentId: null,
        editingBody: "",
        hiddenPreviewBlockIds: [],
        selectedFile: null,
        fileInputKey: state.fileInputKey + 1,
        hasDownloadedJson: false,
        formState: resetFormState,
      };
    }
    case "RESTORE_STORED_STATE":
      return {
        ...state,
        artifact: action.artifact,
        previewDocument: action.previewDocument,
        hiddenPreviewBlockIds: [],
        isSubmitting: false,
        isPreviewing: false,
        isGeneratingRevision: false,
        isSavingDiffReview: false,
        isApplyingRevision: false,
        showTextPreview: false,
        formState: action.formState,
        hasDownloadedJson: action.hasDownloadedJson,
        activeArtifactId: action.activeArtifactId,
        statusMessage: action.statusMessage,
      };
    default:
      return state;
  }
}
