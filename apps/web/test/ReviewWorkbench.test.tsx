import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ReviewWorkbench } from "@/components/ReviewWorkbench";
import { mockArtifact } from "@/lib/mock-data";
import type { AnalysisArtifact, ArtifactComment, ArtifactThread } from "@/lib/types";
import * as api from "@/lib/api";
import reproDuplicateSections from "./fixtures/repro-duplicate-sections.json";

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000",
  fetchAgents: vi.fn().mockResolvedValue([
    {
      agent_id: "similarity",
      display_name: "Similarity Research",
      category: "similarity",
      depends_on: [],
      execution_mode: "multi_step",
      provider_kind: "search",
      description: "Looks for similar public posts and framing overlap.",
      default_enabled: true,
    },
  ]),
  createRun: vi.fn(),
  previewSource: vi.fn(),
  fetchArtifact: vi.fn(),
  cancelRun: vi.fn(),
  importArtifact: vi.fn(),
  createComment: vi.fn().mockResolvedValue(undefined),
  addReply: vi.fn().mockResolvedValue(undefined),
  deleteReply: vi.fn().mockResolvedValue(undefined),
  updateReviewState: vi.fn().mockResolvedValue(undefined),
  updateHumanComment: vi.fn().mockResolvedValue(undefined),
  deleteHumanComment: vi.fn().mockResolvedValue(undefined),
  getExportUrl: vi.fn((_artifactId: string, format: "md" | "json" | "todo") => `http://localhost:8000/export.${format}`),
}));

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return {
        x: 0,
        y: 0,
        width: 160,
        height: 40,
        top: 20,
        right: 160,
        bottom: 60,
        left: 0,
        toJSON() {
          return {};
        },
      };
    },
  });
});

beforeEach(() => {
  window.sessionStorage.clear();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(api.fetchArtifact).mockResolvedValue(mockArtifact);
  vi.mocked(api.previewSource).mockResolvedValue(mockArtifact.document!);
  vi.mocked(api.cancelRun).mockResolvedValue({ ...mockArtifact, status: "canceled" });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ReviewWorkbench", () => {
  it("renders text, threads, and connector paths", async () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByText("How Editorial Teams Can Evaluate AI-Written Posts")).toBeInTheDocument();
    expect(screen.getByTestId("thread-anchor-2")).toBeInTheDocument();
    expect(screen.getAllByTestId("connector-canvas").length).toBeGreaterThan(0);
    expect(await screen.findByTestId("connector-comment-2")).toBeInTheDocument();
  });

  it("shows review buttons and reply controls", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getAllByRole("button", { name: "Accept" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Reject" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Uncertain" }).length).toBeGreaterThan(0);
    expect(screen.getAllByPlaceholderText("Reply to this comment").length).toBeGreaterThan(0);
  });

  it("renders markdown headings, inline emphasis, and code blocks", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByRole("heading", { name: "Inline Markdown Example" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    expect(screen.getByText("const verdict = 'worth revising';").closest("code")?.tagName).toBe("CODE");
  });

  it("opens export URLs", () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Export Markdown" }));
    expect(openSpy).toHaveBeenCalled();
    openSpy.mockRestore();
  });

  it("opens the todo export URL", () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Export Todo" }));

    expect(api.getExportUrl).toHaveBeenCalledWith(mockArtifact.artifact_id, "todo");
    expect(openSpy).toHaveBeenCalled();
    openSpy.mockRestore();
  });

  it("uses a preview-first flow for URL sources", async () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), { target: { value: "url" } });

    expect(screen.getByTestId("draft-url-input")).toBeInTheDocument();
    expect(screen.queryByTestId("draft-text-input")).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId("draft-url-input"), {
      target: { value: "https://example.com/post" },
    });
    fireEvent.click(screen.getByTestId("import-url-button"));

    expect(await screen.findByText("How Editorial Teams Can Evaluate AI-Written Posts")).toBeInTheDocument();
  });

  it("shows new analysis only when an artifact exists", () => {
    const { unmount } = render(<ReviewWorkbench initialArtifact={null} />);

    expect(screen.queryByTestId("new-analysis-button")).not.toBeInTheDocument();

    unmount();
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByTestId("new-analysis-button")).toBeInTheDocument();
  });

  it("defaults the persistence selector to workspace mode", () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    expect(screen.getByTestId("persistence-mode-select")).toHaveValue("workspace");
  });

  it("restores a persisted workspace run by refetching the artifact", async () => {
    window.sessionStorage.setItem(
      "content-evaluation:artifact",
      JSON.stringify({
        version: 2,
        artifactId: mockArtifact.artifact_id,
        artifactPersistenceMode: "workspace",
        artifactStatus: "completed",
        artifactTitle: mockArtifact.document?.title ?? null,
        previewDocument: null,
        formState: {
          sourceType: "text",
          title: "Draft title",
          sourceLabel: "Draft source",
          text: "draft text",
          url: "",
          persistenceMode: "workspace",
          includeDebugTrace: true,
          selectedAgents: ["similarity"],
        },
        hasDownloadedJson: false,
      }),
    );

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith(mockArtifact.artifact_id));
    await waitFor(() =>
      expect(screen.getByTestId("run-status")).toHaveTextContent("Restored completed workspace run from the backend."),
    );
    expect(screen.getByText(mockArtifact.document!.title)).toBeInTheDocument();
  });

  it("falls back to the saved draft state when a session run cannot be refetched", async () => {
    vi.mocked(api.fetchArtifact).mockRejectedValueOnce(new Error("Run not found"));
    window.sessionStorage.setItem(
      "content-evaluation:artifact",
      JSON.stringify({
        version: 2,
        artifactId: "run-missing",
        artifactPersistenceMode: "session",
        artifactStatus: "completed",
        artifactTitle: "Saved session run",
        previewDocument: null,
        formState: {
          sourceType: "text",
          title: "Recovered draft",
          sourceLabel: "Manual input",
          text: "Recovered body",
          url: "",
          persistenceMode: "session",
          includeDebugTrace: true,
          selectedAgents: ["similarity"],
        },
        hasDownloadedJson: false,
      }),
    );

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith("run-missing"));
    await waitFor(() =>
      expect(screen.getByTestId("run-status")).toHaveTextContent(
        "Previous session run is no longer available from the backend. Restored the draft only.",
      ),
    );
    expect(screen.getByTestId("draft-title-input")).toHaveValue("Recovered draft");
    expect(screen.getByTestId("draft-text-input")).toHaveValue("Recovered body");
    expect(screen.queryByTestId("new-analysis-button")).not.toBeInTheDocument();
  });

  it("ignores malformed stored state", async () => {
    window.sessionStorage.setItem("content-evaluation:artifact", JSON.stringify({ version: 2, artifactId: 123 }));

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() => expect(api.fetchAgents).toHaveBeenCalled());
    expect(api.fetchArtifact).not.toHaveBeenCalled();
    expect(screen.getByTestId("draft-title-input")).toHaveValue("");
  });

  it("disables export buttons when no artifact exists", () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    expect(screen.getByRole("button", { name: "Export Todo" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export Markdown" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  });

  it("toggles the active review state back to unreviewed", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("review-state-comment-2-accepted"));

    expect(api.updateReviewState).toHaveBeenCalledWith("comment-2", "unreviewed");
  });

  it("deletes a human reply from the thread UI", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("delete-reply-reply-1"));

    expect(api.deleteReply).toHaveBeenCalledWith("reply-1");
  });

  it("renders the run log below the progress section", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    const progressHeading = screen.getByText("Run progress");
    const runLogHeading = screen.getByText("Run log");

    expect(
      progressHeading.compareDocumentPosition(runLogHeading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("adds active progress styling while a run is live", () => {
    render(<ReviewWorkbench initialArtifact={{ ...mockArtifact, status: "running" }} />);

    const activeTrack = screen.getByTestId("progress-track");
    const activeFill = screen.getByTestId("progress-fill");

    expect(activeTrack.className).toContain("progressTrackActive");
    expect(activeFill.className).toContain("progressFillActive");
  });

  it("shows retry and resume events in the run log", () => {
    const artifact = {
      ...mockArtifact,
      status: "running",
      agent_plan: mockArtifact.agent_plan.map((item) =>
        item.agent_id === "editorial" ? { ...item, status: "running", message: "Retry 1 of 2 after timeout" } : item,
      ),
      events: [
        ...mockArtifact.events,
        {
          id: "event-run-resumed",
          artifact_id: mockArtifact.artifact_id,
          event_type: "run",
          stage: "run",
          status: "resumed",
          message: "Run resumed after worker retry",
          attempt: 2,
          max_attempts: 2,
          snapshot_available: true,
          created_at: new Date().toISOString(),
          metadata: {},
        },
        {
          id: "event-agent-retrying",
          artifact_id: mockArtifact.artifact_id,
          event_type: "agent",
          stage: "editorial",
          status: "retrying",
          message: "Editorial retrying after timeout",
          agent_id: "editorial",
          agent_name: "Editorial",
          attempt: 2,
          max_attempts: 3,
          error_kind: "timeout",
          provider_name: "openai",
          snapshot_available: true,
          created_at: new Date().toISOString(),
          metadata: {},
        },
      ],
    } as AnalysisArtifact;

    render(<ReviewWorkbench initialArtifact={artifact} />);

    expect(screen.getByTestId("run-resumed-note")).toHaveTextContent("Run resumed after worker retry");
    expect(screen.getByText("Editorial retrying after timeout")).toBeInTheDocument();
    expect(screen.getByText("Attempt 2 of 3")).toBeInTheDocument();
  });

  it("renders overlap-heavy fixture blocks without duplicating text", () => {
    const artifact = reproDuplicateSections as AnalysisArtifact;

    render(<ReviewWorkbench initialArtifact={artifact} />);

    const firstRow = screen.getByTestId("document-block-0");
    const blockElement = firstRow.querySelector("[data-block-id]");
    expect(blockElement).not.toBeNull();
    expect(blockElement?.textContent).toBe(artifact.document?.blocks[0]?.text ?? "");
  });

  it("renders overlapping anchors once and marks shared segments for multi-agent highlights", () => {
    const overlapArtifact = buildOverlapArtifact();

    render(<ReviewWorkbench initialArtifact={overlapArtifact} />);

    const firstRow = screen.getByTestId("document-block-0");
    const blockElement = firstRow.querySelector("[data-block-id]");
    expect(blockElement).not.toBeNull();
    expect(blockElement?.textContent).toBe(overlapArtifact.document?.blocks[0]?.text ?? "");

    const sharedSegment = firstRow.querySelector('[data-anchor-count="3"]') as HTMLElement | null;
    expect(sharedSegment).not.toBeNull();
    expect(sharedSegment?.style.background).toContain("linear-gradient");
    expect(sharedSegment?.getAttribute("data-anchor-ids")).toContain("anchor-overlap-1");
  });

  it("renders one thread across adjacent source blocks with continuation highlights", () => {
    const artifact = buildMultiBlockArtifact();

    render(<ReviewWorkbench initialArtifact={artifact} />);

    expect(screen.getByTestId("thread-anchor-multi")).toBeInTheDocument();
    expect(screen.getAllByTestId("comment-comment-multi")).toHaveLength(1);

    const firstRow = screen.getByTestId("document-block-0");
    const secondRow = screen.getByTestId("document-block-1");
    expect(firstRow.querySelector('[data-anchor-ids="anchor-multi"]')).not.toBeNull();
    expect(secondRow.querySelector('[data-anchor-ids="anchor-multi"]')).not.toBeNull();
  });

  it("styles synthetic unmatched blocks distinctly", () => {
    const artifact = buildSyntheticUnmatchedArtifact();

    render(<ReviewWorkbench initialArtifact={artifact} />);

    const unmatchedRow = screen.getByTestId("document-block-2");
    const blockElement = unmatchedRow.querySelector('[data-block-origin="synthetic_unmatched"]');
    expect(blockElement).not.toBeNull();
    expect(blockElement?.className).toContain("documentBlockSynthetic");
  });
});

function buildOverlapArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  const blockText = "Alpha beta gamma delta epsilon zeta.";
  artifact.document = {
    ...artifact.document!,
    text: blockText,
    blocks: [
      {
        id: "block-overlap",
        index: 0,
        text: blockText,
        kind: "paragraph",
        origin: "source",
        markdown: blockText,
        marks: [],
      },
    ],
  };
  artifact.anchors = [
    {
      id: "anchor-overlap-1",
      block_id: "block-overlap",
      start_offset: 0,
      end_offset: 10,
      quote: "Alpha beta",
      match_kind: "source",
      segments: [{ block_id: "block-overlap", start_offset: 0, end_offset: 10 }],
    },
    {
      id: "anchor-overlap-2",
      block_id: "block-overlap",
      start_offset: 0,
      end_offset: 16,
      quote: "Alpha beta gamma",
      match_kind: "source",
      segments: [{ block_id: "block-overlap", start_offset: 0, end_offset: 16 }],
    },
    {
      id: "anchor-overlap-3",
      block_id: "block-overlap",
      start_offset: 0,
      end_offset: 22,
      quote: "Alpha beta gamma delta",
      match_kind: "source",
      segments: [{ block_id: "block-overlap", start_offset: 0, end_offset: 22 }],
    },
  ];
  artifact.threads = [
    buildThread("anchor-overlap-1", "comment-overlap-1", "audience"),
    buildThread("anchor-overlap-2", "comment-overlap-2", "value"),
    buildThread("anchor-overlap-3", "comment-overlap-3", "editorial"),
  ];
  return artifact;
}

function buildThread(
  anchorId: string,
  commentId: string,
  category: ArtifactComment["category"],
): ArtifactThread {
  const anchor = mockAnchor(anchorId);
  return {
    anchor,
    comments: [
      {
        id: commentId,
        artifact_id: "run-demo",
        anchor_id: anchorId,
        author_type: "agent",
        author_label: `${category} agent`,
        category,
        body: `${category} comment`,
        suggestion: null,
        review_state: "unreviewed",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        replies: [],
      },
    ],
  };
}

function mockAnchor(anchorId: string): ArtifactThread["anchor"] {
  if (anchorId === "anchor-overlap-1") {
    return {
      id: "anchor-overlap-1",
      block_id: "block-overlap",
      start_offset: 0,
      end_offset: 10,
      quote: "Alpha beta",
      match_kind: "source",
      segments: [{ block_id: "block-overlap", start_offset: 0, end_offset: 10 }],
    };
  }
  if (anchorId === "anchor-overlap-2") {
    return {
      id: "anchor-overlap-2",
      block_id: "block-overlap",
      start_offset: 0,
      end_offset: 16,
      quote: "Alpha beta gamma",
      match_kind: "source",
      segments: [{ block_id: "block-overlap", start_offset: 0, end_offset: 16 }],
    };
  }
  return {
    id: "anchor-overlap-3",
    block_id: "block-overlap",
    start_offset: 0,
    end_offset: 22,
    quote: "Alpha beta gamma delta",
    match_kind: "source",
    segments: [{ block_id: "block-overlap", start_offset: 0, end_offset: 22 }],
  };
}

function buildMultiBlockArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  artifact.document = {
    ...artifact.document!,
    text: "Alpha paragraph.\n\nBeta paragraph.",
    blocks: [
      {
        id: "block-multi-1",
        index: 0,
        text: "Alpha paragraph.",
        kind: "paragraph",
        origin: "source",
        markdown: "Alpha paragraph.",
        marks: [],
      },
      {
        id: "block-multi-2",
        index: 1,
        text: "Beta paragraph.",
        kind: "paragraph",
        origin: "source",
        markdown: "Beta paragraph.",
        marks: [],
      },
    ],
  };
  artifact.anchors = [
    {
      id: "anchor-multi",
      block_id: "block-multi-1",
      start_offset: 0,
      end_offset: 16,
      quote: "Alpha paragraph.\n\nBeta paragraph.",
      match_kind: "source",
      segments: [
        { block_id: "block-multi-1", start_offset: 0, end_offset: 16 },
        { block_id: "block-multi-2", start_offset: 0, end_offset: 15 },
      ],
    },
  ];
  artifact.threads = [
    {
      anchor: artifact.anchors[0],
      comments: [
        {
          id: "comment-multi",
          artifact_id: artifact.artifact_id,
          anchor_id: "anchor-multi",
          author_type: "agent",
          author_label: "value agent",
          category: "value",
          body: "This thought carries across both paragraphs.",
          suggestion: null,
          review_state: "unreviewed",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          replies: [],
        },
      ],
    },
  ];
  return artifact;
}

function buildSyntheticUnmatchedArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  artifact.document = {
    ...artifact.document!,
    text: "Alpha paragraph.\n\nUnmatched references.\n\nQuoted fallback.",
    blocks: [
      {
        id: "block-source",
        index: 0,
        text: "Alpha paragraph.",
        kind: "paragraph",
        origin: "source",
        markdown: "Alpha paragraph.",
        marks: [],
      },
      {
        id: "block-unmatched-heading",
        index: 1,
        text: "Unmatched references",
        kind: "heading",
        origin: "synthetic_unmatched",
        markdown: "## Unmatched references",
        level: 2,
        marks: [],
      },
      {
        id: "block-unmatched-body",
        index: 2,
        text: "Quoted fallback.",
        kind: "paragraph",
        origin: "synthetic_unmatched",
        markdown: "Quoted fallback.",
        marks: [],
      },
    ],
  };
  return artifact;
}
