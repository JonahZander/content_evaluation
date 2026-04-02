import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ReviewWorkbench } from "@/components/ReviewWorkbench";
import { mockArtifact } from "@/lib/mock-data";
import type { AnalysisArtifact, ArtifactComment, ArtifactThread } from "@/lib/types";
import * as api from "@/lib/api";
import reproDuplicateSections from "./fixtures/repro-duplicate-sections.json";

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000",
  fetchAgents: vi.fn().mockResolvedValue([
    {
      agent_id: "fact_check",
      display_name: "Fact Check",
      category: "fact_check",
      depends_on: [],
      execution_mode: "multi_step",
      provider_kind: "deep_research",
      description: "Verifies claims and overlap research.",
      default_enabled: true,
    },
  ]),
  createRun: vi.fn(),
  createRunFromFile: vi.fn(),
  previewSource: vi.fn(),
  fetchArtifact: vi.fn(),
  appendAgents: vi.fn(),
  cancelRun: vi.fn(),
  generateRevisedMarkdown: vi.fn(),
  updateRevisedMarkdownDiffReview: vi.fn(),
  applyRevisedMarkdown: vi.fn(),
  importArtifact: vi.fn(),
  createComment: vi.fn().mockResolvedValue(undefined),
  addReply: vi.fn().mockResolvedValue(undefined),
  queueResearch: vi.fn().mockResolvedValue(undefined),
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
  vi.mocked(api.createRunFromFile).mockResolvedValue(mockArtifact);
  vi.mocked(api.importArtifact).mockResolvedValue(mockArtifact);
  vi.mocked(api.previewSource).mockResolvedValue(mockArtifact.document!);
  vi.mocked(api.appendAgents).mockResolvedValue(mockArtifact);
  vi.mocked(api.queueResearch).mockResolvedValue(mockArtifact);
  vi.mocked(api.cancelRun).mockResolvedValue({ ...mockArtifact, status: "canceled" });
  vi.mocked(api.generateRevisedMarkdown).mockResolvedValue(buildArtifactWithDiffReview());
  vi.mocked(api.updateRevisedMarkdownDiffReview).mockResolvedValue(buildArtifactWithReviewedDiffs());
  vi.mocked(api.applyRevisedMarkdown).mockResolvedValue(buildArtifactAfterAppliedRevision());
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ReviewWorkbench", () => {
  it("keeps the intake shell visible before any artifact is loaded", () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    expect(screen.getByTestId("source-type-select")).toBeInTheDocument();
    expect(screen.queryByTestId("stop-run-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("export-todo-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("export-markdown-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("export-json-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("progress-track")).not.toBeInTheDocument();
    expect(screen.queryByTestId("review-workbench")).not.toBeInTheDocument();
    expect(screen.queryByTestId("revised-markdown-panel")).not.toBeInTheDocument();
  });

  it("toggles a pasted-text preview before analysis starts", () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("draft-text-input"), {
      target: { value: "Preview this draft before running analysis." },
    });

    fireEvent.click(screen.getByTestId("preview-text-button"));

    expect(screen.getByTestId("text-preview-section")).toBeInTheDocument();
    expect(screen.getByTestId("text-preview-body")).toHaveTextContent("Preview this draft before running analysis.");

    fireEvent.click(screen.getByTestId("preview-text-button"));

    expect(screen.queryByTestId("text-preview-section")).not.toBeInTheDocument();
  });

  it("opens the guided demo artifact from the intake shell", async () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.click(screen.getByTestId("open-demo-artifact-button"));

    await waitFor(() => expect(api.importArtifact).toHaveBeenCalledWith(mockArtifact, expect.any(AbortSignal)));
    await waitFor(() => expect(screen.getByTestId("review-workbench")).toBeInTheDocument());
    expect(screen.getByText("How Editorial Teams Can Evaluate AI-Written Posts")).toBeInTheDocument();
  });

  it("renders the running shell for a fresh in-flight run", () => {
    render(<ReviewWorkbench initialArtifact={buildRunningArtifact()} />);

    expect(screen.getByTestId("running-stage-panel")).toBeInTheDocument();
    expect(screen.getByTestId("progress-track")).toBeInTheDocument();
    expect(screen.getByTestId("running-preview-card")).toHaveTextContent("Waiting for the first agent result.");
    expect(screen.queryByTestId("review-workbench")).not.toBeInTheDocument();
    expect(screen.queryByTestId("review-summary-panel")).not.toBeInTheDocument();
  });

  it("marks completed fact-check as already run in the agent selector", async () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    await waitFor(() => expect(screen.getByTestId("agent-toggle-fact_check")).toBeDisabled());
    expect(screen.getByTestId("agent-lock-fact_check")).toHaveTextContent("Already run");
  });

  it("keeps pasted text visible as a read-only reference after content loads", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    const textInput = screen.getByTestId("draft-text-input");

    expect(textInput).toBeInTheDocument();
    expect(textInput).toHaveAttribute("readonly");
    expect(textInput).toHaveValue(mockArtifact.document?.raw_content ?? "");
  });

  it("cycles through partial findings in the running preview card", () => {
    vi.useFakeTimers();
    try {
      render(<ReviewWorkbench initialArtifact={buildRunningArtifactWithFindings()} />);

      expect(screen.getByTestId("running-preview-card")).toHaveTextContent("First running finding");

      act(() => {
        vi.advanceTimersByTime(5000);
      });

      expect(screen.getByTestId("running-preview-card")).toHaveTextContent("Second running finding");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the running status label stable while the dot slots animate", () => {
    render(<ReviewWorkbench initialArtifact={buildRunningArtifact()} />);

    const label = screen.getByTestId("running-status-label");
    const dots = within(label).getByTestId("running-status-dots");

    expect(label).toHaveTextContent("RUNNING");
    expect(within(dots).getAllByTestId("running-status-dot")).toHaveLength(3);
  });

  it("keeps the running card focused and shows submitted content inline", () => {
    render(<ReviewWorkbench initialArtifact={buildRunningArtifactWithFindings()} />);

    const previewCard = screen.getByTestId("running-preview-card");
    const sourcePreview = screen.getByTestId("running-source-preview");

    expect(previewCard).toHaveTextContent("Live preview");
    expect(within(previewCard).queryByText(/confidence/i)).not.toBeInTheDocument();
    expect(sourcePreview).toHaveTextContent("Editorial teams need a fast way to decide whether a post is original");

    fireEvent.click(screen.getByTestId("running-source-toggle"));

    expect(sourcePreview).not.toHaveTextContent("Editorial teams need a fast way to decide whether a post is original");
    expect(screen.getByTestId("running-source-toggle")).toHaveTextContent("Show submitted content");
  });

  it("keeps append-agent runs in the review shell with compact progress", () => {
    render(<ReviewWorkbench initialArtifact={buildFollowUpRunningArtifact()} />);

    expect(screen.getByTestId("review-workbench")).toBeInTheDocument();
    expect(screen.getByTestId("follow-up-progress")).toBeInTheDocument();
    expect(screen.queryByTestId("running-stage-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("review-summary-panel")).not.toBeInTheDocument();
  });

  it("renders the research panel with a suggested prompt fallback", () => {
    const { unmount } = render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByTestId("research-panel")).toBeInTheDocument();
    expect(screen.getByLabelText("Research prompt")).toHaveValue(
      "Research recent statistics on editorial review workflows to strengthen the opening claim.",
    );

    unmount();

    const artifactWithoutPrompt = structuredClone(mockArtifact);
    artifactWithoutPrompt.agent_results = artifactWithoutPrompt.agent_results.filter(
      (result) => result.category !== "fact_check",
    );
    render(<ReviewWorkbench initialArtifact={artifactWithoutPrompt} />);

    expect(screen.getByLabelText("Research prompt")).toHaveValue("");
  });

  it("keeps research mode in the review shell with inline progress", () => {
    render(<ReviewWorkbench initialArtifact={buildResearchRunningArtifact()} />);

    expect(screen.getByTestId("review-workbench")).toBeInTheDocument();
    expect(screen.getByTestId("follow-up-progress")).toBeInTheDocument();
    expect(within(screen.getByTestId("follow-up-progress")).getByText("Targeted research running")).toBeInTheDocument();
    expect(screen.queryByTestId("running-stage-panel")).not.toBeInTheDocument();
  });

  it("isolates diff review from the rest of the workbench", () => {
    render(<ReviewWorkbench initialArtifact={buildArtifactWithDiffReview()} />);

    expect(screen.getByTestId("diff-review-shell")).toBeInTheDocument();
    expect(screen.queryByTestId("review-workbench")).not.toBeInTheDocument();
    expect(screen.queryByTestId("progress-track")).not.toBeInTheDocument();
    expect(screen.queryByTestId("review-summary-panel")).not.toBeInTheDocument();
  });

  it("keeps imported draft artifacts in the intake shell", () => {
    render(<ReviewWorkbench initialArtifact={buildDraftArtifact()} />);

    expect(screen.getByTestId("source-type-select")).toBeInTheDocument();
    expect(screen.getByTestId("intake-preview-shell")).toBeInTheDocument();
    expect(screen.queryByTestId("review-workbench")).not.toBeInTheDocument();
    expect(screen.queryByTestId("progress-track")).not.toBeInTheDocument();
  });

  it("restores imported in-flight artifacts into the running shell and keeps live polling active", async () => {
    const eventSources: Array<{
      onmessage: ((event: MessageEvent) => void) | null;
      onerror: (() => void) | null;
    }> = [];
    const globalEventSource = globalThis as typeof globalThis & {
      EventSource: typeof EventSource;
    };
    const originalEventSource = globalEventSource.EventSource;

    class SpyEventSource {
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: (() => void) | null = null;

      constructor(_: string) {
        eventSources.push(this);
      }

      close() {}
    }

    globalEventSource.EventSource = SpyEventSource as unknown as typeof EventSource;

    const importedRunningArtifact = buildRunningArtifact();
    vi.mocked(api.importArtifact).mockResolvedValueOnce(importedRunningArtifact);

    try {
      render(<ReviewWorkbench initialArtifact={null} />);
      fireEvent.change(screen.getByTestId("source-type-select"), { target: { value: "artifact" } });

      const file = {
        text: async () => JSON.stringify(importedRunningArtifact),
      } as File;
      fireEvent.change(screen.getByTestId("artifact-import-input"), { target: { files: [file] } });

      await waitFor(() => expect(screen.getByTestId("running-stage-panel")).toBeInTheDocument());
      await waitFor(() => expect(eventSources).toHaveLength(1));

      eventSources[0].onmessage?.({
        data: JSON.stringify({ snapshot_available: true }),
      } as MessageEvent);

      await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith(importedRunningArtifact.artifact_id, undefined));
    } finally {
      globalEventSource.EventSource = originalEventSource;
    }
  });

  it("renders text and threads without connector overlays", async () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByText("How Editorial Teams Can Evaluate AI-Written Posts")).toBeInTheDocument();
    expect(screen.getByTestId("thread-anchor-2")).toBeInTheDocument();
    expect(screen.queryByTestId("connector-canvas")).not.toBeInTheDocument();
    expect(await screen.findByTestId("comment-comment-2")).toBeInTheDocument();
  });

  it("shows review buttons and reply controls", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getAllByRole("button", { name: "Accept" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Reject" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Uncertain" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Add comment" }).length).toBeGreaterThan(0);
    expect(screen.queryByPlaceholderText("Add a comment on this note")).not.toBeInTheDocument();
  });

  it("keeps add comment inline with the agent review actions", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    const acceptButton = screen.getAllByRole("button", { name: "Accept" })[0];
    const addCommentButton = screen.getAllByRole("button", { name: "Add comment" })[0];

    expect(acceptButton.parentElement).toBe(addCommentButton.parentElement);
  });

  it("renders markdown headings, inline emphasis, and code blocks", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByRole("heading", { name: "Inline Markdown Example" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    expect(screen.getByText("const verdict = 'worth revising';").closest("code")?.tagName).toBe("CODE");
  });

  it("renders clickable inline markdown links", () => {
    render(<ReviewWorkbench initialArtifact={buildLinkArtifact()} />);

    const link = screen.getByRole("link", { name: "source reference" });
    expect(link).toHaveAttribute("href", "https://example.com/reference");
  });

  it("keeps one continuous highlight when an anchored span crosses inline links", () => {
    render(<ReviewWorkbench initialArtifact={buildLinkedHighlightArtifact()} />);

    const firstRow = screen.getByTestId("document-block-0");
    const highlights = firstRow.querySelectorAll('[data-anchor-ids="anchor-link-span"]');

    expect(highlights).toHaveLength(1);
    expect(highlights[0]?.textContent).toBe("See source reference for the cited material.");
    expect(highlights[0]?.querySelector('a[href="https://example.com/reference"]')).not.toBeNull();
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
    expect(screen.getAllByRole("button", { name: "Remove section" }).length).toBeGreaterThan(0);
  });

  it("shows URL import guidance until a preview block is removed", async () => {
    vi.mocked(api.previewSource).mockResolvedValue(buildUrlPreviewDocument());
    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), { target: { value: "url" } });
    fireEvent.change(screen.getByTestId("draft-url-input"), {
      target: { value: "https://example.com/post" },
    });
    fireEvent.click(screen.getByTestId("import-url-button"));

    expect(await screen.findByTestId("url-import-guidance")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hide-preview-block-url-block-3"));

    expect(screen.queryByTestId("url-import-guidance")).not.toBeInTheDocument();
  });

  it("toggles imported preview blocks in place", async () => {
    vi.mocked(api.previewSource).mockResolvedValue(buildUrlPreviewDocument());
    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), { target: { value: "url" } });
    fireEvent.change(screen.getByTestId("draft-url-input"), {
      target: { value: "https://example.com/post" },
    });
    fireEvent.click(screen.getByTestId("import-url-button"));

    await waitFor(() => expect(screen.getByTestId("document-title")).toHaveTextContent("Imported URL Preview"));
    fireEvent.click(screen.getByTestId("hide-preview-block-url-block-3"));

    expect(screen.queryByText("Hidden from analysis")).not.toBeInTheDocument();
    expect(screen.queryByText("Section removed from the preview draft")).not.toBeInTheDocument();
    expect(screen.getByTestId("restore-preview-block-url-block-3")).toBeInTheDocument();
    expect(screen.getByTestId("document-block-2").querySelector('[data-preview-hidden="true"]')).not.toBeNull();
    expect(screen.getByText("This section is boilerplate and can be removed.")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("restore-preview-block-url-block-3"));

    expect(screen.getByTestId("hide-preview-block-url-block-3")).toBeInTheDocument();
    expect(screen.getByTestId("document-block-2").querySelector('[data-preview-hidden="true"]')).toBeNull();
  });

  it("restores all hidden preview blocks at once", async () => {
    vi.mocked(api.previewSource).mockResolvedValue(buildUrlPreviewDocument());
    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), { target: { value: "url" } });
    fireEvent.change(screen.getByTestId("draft-url-input"), {
      target: { value: "https://example.com/post" },
    });
    fireEvent.click(screen.getByTestId("import-url-button"));
    await waitFor(() => expect(screen.getByTestId("document-title")).toHaveTextContent("Imported URL Preview"));

    fireEvent.click(screen.getByTestId("hide-preview-block-url-block-1"));
    fireEvent.click(screen.getByTestId("hide-preview-block-url-block-2"));
    fireEvent.click(screen.getByTestId("restore-all-preview-blocks"));

    expect(screen.queryByText("Hidden from analysis")).not.toBeInTheDocument();
  });

  it("submits only visible preview blocks for a URL run", async () => {
    vi.mocked(api.previewSource).mockResolvedValue(buildUrlPreviewDocument());
    vi.mocked(api.createRun).mockResolvedValue(mockArtifact);

    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), { target: { value: "url" } });
    fireEvent.change(screen.getByTestId("draft-url-input"), {
      target: { value: "https://example.com/post" },
    });
    fireEvent.click(screen.getByTestId("import-url-button"));
    await waitFor(() => expect(screen.getByTestId("document-title")).toHaveTextContent("Imported URL Preview"));

    fireEvent.click(screen.getByTestId("hide-preview-block-url-block-2"));
    fireEvent.click(screen.getByTestId("analyze-button"));

    await waitFor(() => expect(api.createRun).toHaveBeenCalled());
    expect(api.createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceType: "url",
        url: "https://example.com/post",
        text: [
          "## Imported URL Preview",
          "This section is boilerplate and can be removed.",
          "See [source reference](https://example.com/reference) for the cited material.",
        ].join("\n\n"),
      }),
      expect.any(AbortSignal),
    );
  });

  it("does not show URL import guidance once an artifact exists", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.queryByTestId("url-import-guidance")).not.toBeInTheDocument();
  });

  it("shows new analysis only when an artifact exists", () => {
    const { unmount } = render(<ReviewWorkbench initialArtifact={null} />);

    expect(screen.queryByTestId("new-analysis-button")).not.toBeInTheDocument();

    unmount();
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByTestId("new-analysis-button")).toBeInTheDocument();
  });

  it("defaults new analyses to workspace persistence mode", async () => {
    vi.mocked(api.createRun).mockResolvedValueOnce(mockArtifact);

    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("draft-text-input"), {
      target: { value: "Persist this in the default mode." },
    });
    fireEvent.click(screen.getByTestId("analyze-button"));

    await waitFor(() =>
      expect(api.createRun).toHaveBeenCalledWith(
        expect.objectContaining({
          persistenceMode: "workspace",
        }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("sends file uploads through the multipart createRunFromFile path with form fields", async () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), { target: { value: "file" } });
    await waitFor(() => expect(screen.getByTestId("agent-toggle-fact_check")).toBeChecked());

    const uploadedFile = new File(["# Uploaded draft\n\nThis draft is ready for review."], "uploaded-draft.md", {
      type: "text/markdown",
    });

    fireEvent.change(screen.getByTestId("draft-file-input"), {
      target: { files: [uploadedFile] },
    });
    fireEvent.click(screen.getByTestId("analyze-button"));

    await waitFor(() =>
      expect(api.createRunFromFile).toHaveBeenCalledWith(
        uploadedFile,
        expect.objectContaining({
          selectedAgents: ["fact_check"],
          persistenceMode: "workspace",
          includeDebugTrace: true,
          title: "Uploaded draft",
        }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("serializes multipart file runs with repeated agent fields and form values", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockArtifact), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    try {
      const { createRunFromFile } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
      const uploadedFile = new File(["# Multipart draft\n\nThis is the body."], "multipart-draft.md", {
        type: "text/markdown",
      });

      await createRunFromFile(
        uploadedFile,
        {
          selectedAgents: ["fact_check", "editorial"],
          persistenceMode: "workspace",
          includeDebugTrace: false,
          title: "Multipart draft",
        },
        new AbortController().signal,
      );

      expect(fetchSpy).toHaveBeenCalledWith(
        `${api.API_BASE_URL}/api/v1/runs`,
        expect.objectContaining({
          method: "POST",
          body: expect.any(FormData),
        }),
      );

      const requestInit = fetchSpy.mock.calls[0]?.[1] as RequestInit;
      const body = requestInit.body as FormData;

      expect(body).toBeInstanceOf(FormData);
      expect(body.get("file")).toBe(uploadedFile);
      expect(body.getAll("selected_agents")).toEqual(["fact_check", "editorial"]);
      expect(body.get("persistence_mode")).toBe("workspace");
      expect(body.get("include_debug_trace")).toBe("false");
      expect(body.get("title")).toBe("Multipart draft");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("restores a persisted workspace run by refetching the artifact", async () => {
    window.sessionStorage.setItem(
      "content-evaluation:artifact",
      JSON.stringify({
        version: 3,
        artifactId: mockArtifact.artifact_id,
        artifactPersistenceMode: "workspace",
        artifactStatus: "completed",
        artifactTitle: mockArtifact.document?.title ?? null,
        draftRecovery: null,
        formState: {
          sourceType: "text",
          title: "Draft title",
          sourceLabel: "Draft source",
          text: "draft text",
          url: "",
          persistenceMode: "workspace",
          includeDebugTrace: true,
          selectedAgents: ["fact_check"],
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
        version: 3,
        artifactId: "run-missing",
        artifactPersistenceMode: "session",
        artifactStatus: "completed",
        artifactTitle: "Saved session run",
        draftRecovery: {
          mode: "intake",
          sourceType: "text",
          sourceLabel: "Manual input",
          title: "Recovered draft",
          url: "",
          text: "Recovered body",
        },
        formState: {
          sourceType: "text",
          title: "Recovered draft",
          sourceLabel: "Manual input",
          text: "Recovered body",
          url: "",
          persistenceMode: "session",
          includeDebugTrace: true,
          selectedAgents: ["fact_check"],
        },
        hasDownloadedJson: false,
      }),
    );

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith("run-missing"));
    await waitFor(() =>
      expect(screen.getByTestId("run-status")).toHaveTextContent(
        "Restored draft from session storage.",
      ),
    );
    expect(screen.getByTestId("draft-text-input")).toHaveValue("Recovered body");
    expect(screen.queryByTestId("new-analysis-button")).not.toBeInTheDocument();
  });

  it("restores stale diff-review state into the review shell when the backend artifact is gone", async () => {
    vi.mocked(api.fetchArtifact).mockRejectedValueOnce(new Error("Run not found"));
    window.sessionStorage.setItem(
      "content-evaluation:artifact",
      JSON.stringify({
        version: 3,
        artifactId: "run-missing",
        artifactPersistenceMode: "workspace",
        artifactStatus: "completed",
        artifactTitle: "Saved revised draft",
        artifactPhase: "diff_review",
        draftRecovery: {
          mode: "intake",
          sourceType: "text",
          sourceLabel: "Manual input",
          title: "Recovered draft",
          url: "",
          text: "Recovered body",
        },
        formState: {
          sourceType: "text",
          title: "Recovered draft",
          sourceLabel: "Manual input",
          text: "Recovered body",
          url: "",
          persistenceMode: "workspace",
          includeDebugTrace: true,
          selectedAgents: ["fact_check"],
        },
        hasDownloadedJson: false,
      }),
    );

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith("run-missing"));
    await waitFor(() =>
      expect(screen.getByTestId("run-status")).toHaveTextContent(
        "Previous revised markdown review is no longer available from the backend. Restored the review shell from the saved draft.",
      ),
    );
    expect(screen.getByTestId("review-workbench")).toBeInTheDocument();
    expect(screen.queryByTestId("source-type-select")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("document-block-0")).getByText("Recovered body")).toBeInTheDocument();
  });

  it("restores an intake URL preview from bounded draft-recovery metadata", async () => {
    window.sessionStorage.setItem(
      "content-evaluation:artifact",
      JSON.stringify({
        version: 3,
        artifactId: null,
        artifactPersistenceMode: null,
        artifactStatus: null,
        artifactTitle: null,
        artifactPhase: "intake",
        draftRecovery: {
          mode: "preview",
          sourceType: "url",
          sourceLabel: "https://example.com/recovered",
          title: "Recovered URL Preview",
          url: "https://example.com/recovered",
          text: "Recovered preview body",
        },
        formState: {
          sourceType: "url",
          title: "",
          sourceLabel: "Manual input",
          text: "",
          url: "",
          persistenceMode: "workspace",
          includeDebugTrace: true,
          selectedAgents: ["fact_check"],
        },
        hasDownloadedJson: false,
      }),
    );

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() =>
      expect(screen.getByTestId("run-status")).toHaveTextContent(
        "Restored imported draft preview for Recovered URL Preview.",
      ),
    );
    expect(screen.getByTestId("intake-preview-shell")).toBeInTheDocument();
    expect(within(screen.getByTestId("document-block-0")).getByText("Recovered preview body")).toBeInTheDocument();
    expect(api.fetchArtifact).not.toHaveBeenCalled();
  });

  it("ignores legacy stored full-artifact payloads", async () => {
    window.sessionStorage.setItem("content-evaluation:artifact", JSON.stringify(mockArtifact));

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() => expect(api.fetchAgents).toHaveBeenCalled());
    expect(api.fetchArtifact).not.toHaveBeenCalled();
    expect(screen.getByTestId("draft-text-input")).toHaveValue("");
  });

  it("ignores malformed stored state", async () => {
    window.sessionStorage.setItem("content-evaluation:artifact", JSON.stringify({ version: 2, artifactId: 123 }));

    render(<ReviewWorkbench initialArtifact={null} />);

    await waitFor(() => expect(api.fetchAgents).toHaveBeenCalled());
    expect(api.fetchArtifact).not.toHaveBeenCalled();
    expect(screen.getByTestId("draft-text-input")).toHaveValue("");
  });

  it("hides export buttons when no artifact exists", () => {
    render(<ReviewWorkbench initialArtifact={null} />);

    expect(screen.queryByRole("button", { name: "Export Todo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export Markdown" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export JSON" })).not.toBeInTheDocument();
  });

  it("toggles the active review state back to unreviewed", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("review-state-comment-2-accepted"));

    expect(api.updateReviewState).toHaveBeenCalledWith("comment-2", "unreviewed", expect.any(AbortSignal));
  });

  it("generates revised markdown only after accepted suggestions exist", () => {
    const artifactWithoutAcceptedSuggestions = structuredClone(mockArtifact);
    artifactWithoutAcceptedSuggestions.threads = artifactWithoutAcceptedSuggestions.threads.map((thread) => ({
      ...thread,
      comments: thread.comments.map((comment) => ({
        ...comment,
        review_state: "unreviewed",
      })),
    }));

    const { unmount } = render(<ReviewWorkbench initialArtifact={artifactWithoutAcceptedSuggestions} />);

    expect(screen.queryByTestId("revision-cta-top")).not.toBeInTheDocument();
    expect(screen.queryByTestId("revision-cta-bottom")).not.toBeInTheDocument();

    unmount();
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByTestId("revision-cta-top")).toBeInTheDocument();
    expect(screen.getByTestId("revision-cta-bottom")).toBeInTheDocument();
  });

  it("generates a revised markdown candidate and shows the diff review panel", async () => {
    const generatedArtifact = buildArtifactWithDiffReview();
    vi.mocked(api.generateRevisedMarkdown).mockResolvedValueOnce(generatedArtifact);

    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("apply-changes-button-bottom"));

    await waitFor(() =>
      expect(api.generateRevisedMarkdown).toHaveBeenCalledWith({
        artifactId: mockArtifact.artifact_id,
        mode: "surgical",
        directionPrompt: undefined,
      }, expect.any(AbortSignal)),
    );
    expect(await screen.findByTestId("revised-markdown-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("diff-view-toggle")).not.toBeInTheDocument();
    expect(screen.getByTestId("diff-item-status-diff-1")).toHaveTextContent("pending");
    expect(screen.getByTestId("inline-diff-view")).toBeInTheDocument();
    expect(screen.queryByTestId("diff-summary-diff-1")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Accept at least one diff item to enable apply. Pending or unreviewed changes will remain unchanged until they are reviewed.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply accepted changes" })).toBeDisabled();
  });

  it("opens rewrite mode with a direction prompt and labels the diff review mode", async () => {
    const generatedArtifact = buildArtifactWithRewriteDiffReview();
    vi.mocked(api.generateRevisedMarkdown).mockResolvedValueOnce(generatedArtifact);

    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("rewrite-draft-button-top"));
    fireEvent.change(screen.getByTestId("rewrite-direction-input-top"), {
      target: { value: "Lead with the strongest finding." },
    });
    fireEvent.click(screen.getByTestId("submit-rewrite-draft-button-top"));

    await waitFor(() =>
      expect(api.generateRevisedMarkdown).toHaveBeenCalledWith({
        artifactId: mockArtifact.artifact_id,
        mode: "rewrite",
        directionPrompt: "Lead with the strongest finding.",
      }, expect.any(AbortSignal)),
    );
    expect(await screen.findByText("Rewrite draft")).toBeInTheDocument();
    expect(screen.getByText("Direction: Lead with the strongest finding.")).toBeInTheDocument();
    expect(screen.getByTestId("diff-view-toggle-side-by-side").className).toContain("diffViewToggleActive");
    expect(screen.getByRole("button", { name: "Apply full revision" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Discard revision" })).toBeInTheDocument();
    expect(screen.queryByTestId("diff-item-diff-1")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("diff-view-toggle-inline"));

    expect(screen.getByTestId("diff-item-diff-1")).toBeInTheDocument();
  });

  it("saves accepted diff changes and applies them while pending diffs stay untouched", async () => {
    const artifactWithDiff = buildArtifactWithPartialReviewedDiffs();
    const reviewedArtifact = buildArtifactWithAcceptedAndPendingDiffs();
    vi.mocked(api.updateRevisedMarkdownDiffReview).mockResolvedValueOnce(reviewedArtifact);
    vi.mocked(api.applyRevisedMarkdown).mockResolvedValueOnce(buildArtifactAfterAppliedRevision());

    render(<ReviewWorkbench initialArtifact={artifactWithDiff} />);

    fireEvent.click(screen.getByTestId("diff-decision-diff-1-accepted"));

    await waitFor(() =>
      expect(api.updateRevisedMarkdownDiffReview).toHaveBeenCalledWith(artifactWithDiff.artifact_id, [
        { diffId: "diff-1", decision: "accepted" },
      ], expect.any(AbortSignal)),
    );

    expect(screen.getByTestId("diff-item-status-diff-2")).toHaveTextContent("pending");
    expect(
      screen.getByText(
        "Apply will include 1 accepted change and leave 1 pending or unreviewed diff item unchanged.",
      ),
    ).toBeInTheDocument();

    const applyButton = await screen.findByRole("button", { name: "Apply accepted changes" });
    expect(applyButton).toBeEnabled();

    fireEvent.click(applyButton);

    await waitFor(() => expect(api.applyRevisedMarkdown).toHaveBeenCalledWith(artifactWithDiff.artifact_id, expect.any(AbortSignal)));
    expect(screen.queryByTestId("diff-review-shell")).not.toBeInTheDocument();
    expect(screen.getByTestId("review-workbench")).toBeInTheDocument();
  });

  it("returns to the main review shell when a stale diff review cannot be applied", async () => {
    const reviewedArtifact = buildArtifactWithReviewedDiffs();
    vi.mocked(api.applyRevisedMarkdown).mockRejectedValueOnce(
      new Error("No revised markdown diff is available to apply."),
    );
    vi.mocked(api.fetchArtifact).mockResolvedValueOnce(mockArtifact);

    render(<ReviewWorkbench initialArtifact={reviewedArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Apply accepted changes" }));

    await waitFor(() => expect(api.applyRevisedMarkdown).toHaveBeenCalledWith(reviewedArtifact.artifact_id, expect.any(AbortSignal)));
    await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith(reviewedArtifact.artifact_id));
    await waitFor(() => expect(screen.getByTestId("review-workbench")).toBeInTheDocument());
    expect(screen.queryByTestId("diff-review-shell")).not.toBeInTheDocument();
    expect(screen.getByTestId("run-status")).toHaveTextContent(
      "Revised markdown review is no longer available. Returned to the main review view.",
    );
  });

  it("discards a side-by-side revision by rejecting every diff without applying", async () => {
    const rewriteArtifact = buildArtifactWithRewriteDiffReview();
    vi.mocked(api.updateRevisedMarkdownDiffReview).mockResolvedValueOnce(buildArtifactWithRejectedRewriteDiffs());

    render(<ReviewWorkbench initialArtifact={rewriteArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Discard revision" }));

    await waitFor(() =>
      expect(api.updateRevisedMarkdownDiffReview).toHaveBeenCalledWith(rewriteArtifact.artifact_id, [
        { diffId: "diff-1", decision: "rejected" },
      ], expect.any(AbortSignal)),
    );
    expect(api.applyRevisedMarkdown).not.toHaveBeenCalled();
    expect(screen.getByTestId("diff-view-toggle-side-by-side")).toBeInTheDocument();
  });

  it("shares rewrite state between the top and bottom revision actions", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("rewrite-draft-button-bottom"));

    const topInput = screen.getByTestId("rewrite-direction-input-top");
    const bottomInput = screen.getByTestId("rewrite-direction-input-bottom");

    fireEvent.change(bottomInput, {
      target: { value: "Lead with the clearest argument first." },
    });

    expect(topInput).toHaveValue("Lead with the clearest argument first.");
    expect(bottomInput).toHaveValue("Lead with the clearest argument first.");
  });

  it("renders surgical diffs as one inline article surface with word-level highlights", () => {
    render(<ReviewWorkbench initialArtifact={buildArtifactWithWordLevelDiffReview()} />);

    expect(screen.getByTestId("inline-diff-view")).toBeInTheDocument();
    expect(screen.queryByTestId("diff-view-toggle")).not.toBeInTheDocument();
    expect(screen.queryByTestId("diff-summary-diff-word")).not.toBeInTheDocument();

    const diffItem = screen.getByTestId("diff-item-diff-word");
    const removed = diffItem.querySelector('[class*="inlineDiffRemoved"]') as HTMLElement | null;
    const addedSegments = diffItem.querySelectorAll('[class*="inlineDiffAdded"]');
    const added = Array.from(addedSegments).find((segment) => segment.textContent === "concrete ") as HTMLElement | undefined;

    expect(removed).not.toBeNull();
    expect(removed?.textContent).toBe("vague ");
    expect(removed?.className).toContain("inlineDiffRemoved");
    expect(added).toBeDefined();
    expect(added?.className).toContain("inlineDiffAdded");
    expect(screen.getByText("editorial instincts into a")).toBeInTheDocument();
  });

  it("blocks additive analysis while revised markdown review is pending", () => {
    render(<ReviewWorkbench initialArtifact={buildArtifactWithDiffReview()} />);

    expect(screen.queryByTestId("analyze-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("diff-review-shell")).toBeInTheDocument();
    expect(screen.queryByTestId("revision-cta-top")).not.toBeInTheDocument();
    expect(screen.queryByTestId("revision-cta-bottom")).not.toBeInTheDocument();
    expect(api.appendAgents).not.toHaveBeenCalled();
  });

  it("queues additional analysis for a terminal artifact without replacing it", () => {
    render(<ReviewWorkbench initialArtifact={buildAppendableArtifact()} />);

    fireEvent.click(screen.getByRole("button", { name: "Add selected analysis" }));

    expect(api.appendAgents).toHaveBeenCalledWith({
      artifactId: mockArtifact.artifact_id,
      selectedAgents: ["editorial"],
    }, expect.any(AbortSignal));
  });

  it("deletes a human reply from the thread UI", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("delete-reply-reply-1"));

    expect(api.deleteReply).toHaveBeenCalledWith("reply-1", expect.any(AbortSignal));
  });

  it("renders the run log below the progress section", () => {
    render(<ReviewWorkbench initialArtifact={buildRunningArtifact()} />);

    const progressHeading = screen.getByText("Run progress");
    const runLogToggle = screen.getByText(/Run log/);

    expect(progressHeading.compareDocumentPosition(runLogToggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders the review summary panel above the text pane", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    expect(screen.getByTestId("review-summary-panel")).toBeInTheDocument();
    expect(screen.getByText("Research summary")).toBeInTheDocument();
    expect(screen.getByText("Editorial review systems for AI content")).toBeInTheDocument();
  });

  it("renders unavailable sub-scores as em dashes while keeping real zero values as 0%", () => {
    const missingScoresArtifact = structuredClone(mockArtifact);
    if (missingScoresArtifact.summary === null) {
      throw new Error("Expected summary data in mock artifact");
    }
    missingScoresArtifact.summary.novelty_score = null;
    missingScoresArtifact.summary.ai_likelihood = null;

    const { unmount } = render(<ReviewWorkbench initialArtifact={missingScoresArtifact} />);

    expect(screen.getByText("Novelty").closest("article")).toHaveTextContent("—");
    expect(screen.getByText("Human voice").closest("article")).toHaveTextContent("—");

    unmount();

    const zeroScoresArtifact = structuredClone(mockArtifact);
    if (zeroScoresArtifact.summary === null) {
      throw new Error("Expected summary data in mock artifact");
    }
    zeroScoresArtifact.summary.novelty_score = 0;
    zeroScoresArtifact.summary.ai_likelihood = 0;

    render(<ReviewWorkbench initialArtifact={zeroScoresArtifact} />);

    expect(screen.getByText("Novelty").closest("article")).toHaveTextContent("0%");
    expect(screen.getByText("Human voice").closest("article")).toHaveTextContent("0%");
  });

  it("renders fact-check details in the comment thread rail", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    const factCheckCard = screen.getByTestId("fact-check-details-comment-fact-1");

    expect(screen.getByTestId("comment-comment-fact-1")).toBeInTheDocument();
    expect(within(factCheckCard).getByText("Claim: Editorial teams need a fast way to decide whether a post is original, useful, and worth reader attention.")).toBeInTheDocument();
    expect(within(factCheckCard).getByText("Verdict: SUPPORTED")).toBeInTheDocument();
    expect(within(factCheckCard).getByText("Supported by public examples of editorial review workflows and citation-backed evaluation guidance.")).toBeInTheDocument();
    const sourceLink = within(factCheckCard).getByRole("link", { name: "example.com" });
    expect(sourceLink).toBeInTheDocument();
    expect(sourceLink).toHaveAttribute("href", "https://example.com/editorial-review");
    expect(sourceLink).toHaveAttribute("target", "_blank");
  });

  it("replaces inline fact-check URLs with hostname links while preserving the surrounding copy", () => {
    const artifact = structuredClone(mockArtifact) as AnalysisArtifact;
    const factCheckComment = artifact.threads
      .flatMap((thread) => thread.comments)
      .find((comment) => comment.id === "comment-fact-1");

    if (!factCheckComment) {
      throw new Error("Missing fact-check comment in mock artifact");
    }

    factCheckComment.body = "Cross-check Reuters at https://www.reuters.com/world and the workflow note at https://example.com/editorial-review before publishing.";
    factCheckComment.sources = [
      "https://www.reuters.com/world",
      "https://example.com/editorial-review",
    ];
    factCheckComment.metadata = {
      ...factCheckComment.metadata,
      source_links: [
        "https://www.reuters.com/world",
        "https://example.com/editorial-review",
      ],
    };

    render(<ReviewWorkbench initialArtifact={artifact} />);

    const commentCard = screen.getByTestId("comment-comment-fact-1");
    const body = commentCard.querySelector("p");

    expect(body).not.toBeNull();
    expect(body).toHaveTextContent(
      "Cross-check Reuters at reuters.com and the workflow note at example.com before publishing.",
    );

    const reutersLink = within(body as HTMLParagraphElement).getByRole("link", { name: "reuters.com" });
    const exampleLink = within(body as HTMLParagraphElement).getByRole("link", { name: "example.com" });

    expect(reutersLink).toHaveAttribute("href", "https://www.reuters.com/world");
    expect(reutersLink).toHaveAttribute("target", "_blank");
    expect(exampleLink).toHaveAttribute("href", "https://example.com/editorial-review");
    expect(exampleLink).toHaveAttribute("target", "_blank");
    expect(within(commentCard).queryByText(/https:\/\/www\.reuters\.com\/world/)).not.toBeInTheDocument();
    expect(within(commentCard).queryByText(/https:\/\/example\.com\/editorial-review/)).not.toBeInTheDocument();
  });

  it("adds active progress styling while a run is live", () => {
    render(<ReviewWorkbench initialArtifact={buildRunningArtifact()} />);

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
    const artifact = reproDuplicateSections as unknown as AnalysisArtifact;

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
    expect(sharedSegment?.style.background).toContain("rgba(111, 118, 126, 0.18)");
    expect(sharedSegment?.getAttribute("data-anchor-ids")).toContain("anchor-overlap-1");
  });

  it("reveals the inline comment composer only after clicking add comment", () => {
    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("reply-toggle-comment-2"));

    expect(screen.getByTestId("reply-input-comment-2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save comment" })).toBeInTheDocument();
  });

  it("uses the follow-up action path for research comments", async () => {
    const artifact = buildResearchCommentArtifact();
    vi.mocked(api.queueResearch).mockResolvedValueOnce(mockArtifact);

    render(<ReviewWorkbench initialArtifact={artifact} />);

    expect(screen.getByTestId("reply-toggle-comment-research-1")).toHaveTextContent("Ask follow-up");
    fireEvent.click(screen.getByTestId("reply-toggle-comment-research-1"));

    expect(screen.getByTestId("reply-input-comment-research-1")).toHaveAttribute(
      "placeholder",
      "Ask a follow-up question about this finding",
    );
    expect(screen.getByRole("button", { name: "Save follow-up" })).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("reply-input-comment-research-1"), {
      target: { value: "What recent data supports this?" },
    });
    fireEvent.click(screen.getByTestId("reply-submit-comment-research-1"));

    await waitFor(() =>
      expect(api.queueResearch).toHaveBeenCalledWith({
        artifactId: artifact.artifact_id,
        prompt: "What recent data supports this?",
        anchorId: "anchor-research-1",
        commentId: "comment-research-1",
      }, expect.any(AbortSignal)),
    );
    expect(api.addReply).not.toHaveBeenCalled();
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

  it("shows a local error on the analyze button when run creation fails", async () => {
    vi.mocked(api.createRun).mockRejectedValueOnce(new Error("Backend unavailable."));

    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("draft-text-input"), {
      target: { value: "Some article text." },
    });

    fireEvent.click(screen.getByTestId("analyze-button"));

    await waitFor(() =>
      expect(screen.getByTestId("submit-local-error")).toHaveTextContent("Backend unavailable."),
    );
  });

  it("shows a local error near the URL import button when preview fails", async () => {
    vi.mocked(api.previewSource).mockRejectedValueOnce(new Error("Could not fetch URL."));

    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), {
      target: { value: "url" },
    });
    fireEvent.change(screen.getByTestId("draft-url-input"), {
      target: { value: "https://example.com/post" },
    });
    fireEvent.click(screen.getByTestId("import-url-button"));

    await waitFor(() =>
      expect(screen.getByTestId("url-import-local-error")).toHaveTextContent("Could not fetch URL."),
    );
  });

  it("shows a local error near the artifact import input when import fails", async () => {
    vi.mocked(api.importArtifact).mockRejectedValueOnce(new Error("Invalid artifact file."));

    render(<ReviewWorkbench initialArtifact={null} />);

    fireEvent.change(screen.getByTestId("source-type-select"), {
      target: { value: "artifact" },
    });

    const file = { text: async () => '{ "invalid": true }' } as File;
    fireEvent.change(screen.getByTestId("artifact-import-input"), {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(screen.getByTestId("artifact-import-local-error")).toHaveTextContent("Invalid artifact file."),
    );
  });

  it("shows a local error near the analyze button when append-agent fails", async () => {
    vi.mocked(api.appendAgents).mockRejectedValueOnce(new Error("Agent queue full."));

    render(<ReviewWorkbench initialArtifact={buildAppendableArtifact()} />);

    fireEvent.click(screen.getByTestId("analyze-button"));

    await waitFor(() =>
      expect(screen.getByTestId("submit-local-error")).toHaveTextContent("Agent queue full."),
    );
  });

  it("shows a local error in the research panel when targeted research fails", async () => {
    vi.mocked(api.queueResearch).mockRejectedValueOnce(new Error("Research quota exceeded."));

    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Research prompt" }), {
      target: { value: "What is the source?" },
    });
    fireEvent.click(screen.getByTestId("research-submit-button"));

    await waitFor(() =>
      expect(screen.getByTestId("research-local-error")).toHaveTextContent("Research quota exceeded."),
    );
  });

  it("shows a per-comment local error when a review-state update fails", async () => {
    vi.mocked(api.updateReviewState).mockRejectedValueOnce(new Error("State update failed."));

    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    const thread = screen.getAllByTestId(/^thread-/)[0];
    const acceptButtons = within(thread).getAllByRole("button", { name: /^Accept$/i });
    fireEvent.click(acceptButtons[0]);

    await waitFor(() =>
      expect(screen.getByTestId(/thread-action-local-error/)).toHaveTextContent("State update failed."),
    );
  });

  it("shows a local error when revised-markdown generation fails", async () => {
    vi.mocked(api.generateRevisedMarkdown).mockRejectedValueOnce(new Error("Model timed out."));

    render(<ReviewWorkbench initialArtifact={mockArtifact} />);

    fireEvent.click(screen.getByTestId("apply-changes-button-bottom"));

    await waitFor(() =>
      expect(screen.getByTestId("revised-markdown-local-error")).toHaveTextContent("Model timed out."),
    );
  });

  it("shows a local error when a diff decision save fails", async () => {
    vi.mocked(api.updateRevisedMarkdownDiffReview).mockRejectedValueOnce(new Error("Save conflict."));

    render(<ReviewWorkbench initialArtifact={buildArtifactWithDiffReview()} />);

    fireEvent.click(screen.getByTestId("diff-decision-diff-1-accepted"));

    await waitFor(() =>
      expect(screen.getByTestId("revised-markdown-local-error")).toHaveTextContent("Save conflict."),
    );
  });

  it("shows a local error when revised-markdown apply fails without stale-review recovery", async () => {
    const reviewedArtifact = buildArtifactWithReviewedDiffs();
    vi.mocked(api.applyRevisedMarkdown).mockRejectedValueOnce(new Error("Apply error."));
    vi.mocked(api.fetchArtifact).mockRejectedValueOnce(new Error("Not found"));

    render(<ReviewWorkbench initialArtifact={reviewedArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Apply accepted changes" }));

    await waitFor(() =>
      expect(screen.getByTestId("revised-markdown-local-error")).toHaveTextContent("Apply error."),
    );
  });

  it("stale diff review recovery still returns to the review shell after error UX is in place", async () => {
    const reviewedArtifact = buildArtifactWithReviewedDiffs();
    vi.mocked(api.applyRevisedMarkdown).mockRejectedValueOnce(
      new Error("No revised markdown diff is available to apply."),
    );
    vi.mocked(api.fetchArtifact).mockResolvedValueOnce(mockArtifact);

    render(<ReviewWorkbench initialArtifact={reviewedArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Apply accepted changes" }));

    await waitFor(() => expect(screen.getByTestId("review-workbench")).toBeInTheDocument());
    expect(screen.queryByTestId("diff-review-shell")).not.toBeInTheDocument();
    expect(screen.queryByTestId("revised-markdown-local-error")).not.toBeInTheDocument();
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

function buildDraftArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  artifact.status = "draft";
  artifact.source = {
    ...artifact.source,
    imported: true,
  };
  artifact.agent_plan = [];
  artifact.agent_results = [];
  artifact.anchors = [];
  artifact.threads = [];
  artifact.summary = null;
  artifact.review_summary = null;
  artifact.revised_document = null;
  artifact.diff_review = null;
  artifact.events = [];
  return artifact;
}

function buildAppendableArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  artifact.run_config = {
    ...artifact.run_config,
    selected_agents: ["editorial"],
    resolved_agents: ["editorial"],
  };
  artifact.agent_plan = artifact.agent_plan.map((item) =>
    item.agent_id === "editorial"
      ? { ...item, status: "pending" }
      : item,
  );
  artifact.agent_results = artifact.agent_results.filter((item) => item.agent_id !== "editorial");
  artifact.threads = artifact.threads.filter((thread) => thread.comments[0]?.category !== "editorial");
  return artifact;
}

function buildRunningArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  artifact.status = "running";
  artifact.agent_plan = artifact.agent_plan.map((item, index) => ({
    ...item,
    status: index === 0 ? "running" : "pending",
    message: index === 0 ? "Fact Check is gathering sources" : "Queued",
  }));
  artifact.agent_results = [];
  artifact.anchors = [];
  artifact.threads = [];
  artifact.summary = null;
  artifact.review_summary = null;
  artifact.revised_document = null;
  artifact.diff_review = null;
  artifact.events = [
    {
      id: "event-running-started",
      artifact_id: artifact.artifact_id,
      event_type: "run",
      stage: "run",
      status: "started",
      message: "Run started",
      progress: 0.32,
      snapshot_available: true,
      created_at: new Date().toISOString(),
      metadata: {},
    },
  ];
  return artifact;
}

function buildRunningArtifactWithFindings(): AnalysisArtifact {
  const artifact = buildRunningArtifact();
  artifact.agent_results = [
    {
      agent_id: "ai_likelihood",
      category: "ai_likelihood",
      status: "running",
      findings: [
        {
          id: "finding-running-1",
          category: "ai_likelihood",
          agent_name: "ai_likelihood",
          anchor_ids: [],
          rationale: "First running finding",
          confidence: 0.41,
          model_name: "mock-analysis",
          suggestion: "First suggestion",
          sources: [],
          metadata: {},
        },
      ],
      summary: null,
      raw_output: {},
      metadata: {},
    },
    {
      agent_id: "editorial",
      category: "editorial",
      status: "running",
      findings: [
        {
          id: "finding-running-2",
          category: "editorial",
          agent_name: "editorial",
          anchor_ids: [],
          rationale: "Second running finding",
          confidence: 0.66,
          model_name: "mock-analysis",
          suggestion: "Second suggestion",
          sources: [],
          metadata: {},
        },
      ],
      summary: null,
      raw_output: {},
      metadata: {},
    },
  ];
  artifact.events = [
    ...artifact.events,
    {
      id: "event-running-finding",
      artifact_id: artifact.artifact_id,
      event_type: "agent",
      stage: "ai_likelihood",
      status: "completed",
      message: "AI Likelihood completed",
      agent_id: "ai_likelihood",
      agent_name: "AI Likelihood",
      model_name: "mock-analysis",
      snapshot_available: true,
      created_at: new Date().toISOString(),
      metadata: {},
    },
  ];
  return artifact;
}

function buildFollowUpRunningArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  artifact.status = "running";
  artifact.summary = null;
  artifact.review_summary = null;
  artifact.diff_review = null;
  artifact.revised_document = null;
  artifact.events = [
    ...artifact.events,
    {
      id: "event-follow-up-queued",
      artifact_id: artifact.artifact_id,
      event_type: "run",
      stage: "run",
      status: "queued",
      message: "Additional analysis queued",
      progress: 0.64,
      snapshot_available: true,
      created_at: new Date().toISOString(),
      metadata: {
        mode: "append_agents",
        append_agent_ids: ["editorial"],
      },
    },
  ];
  return artifact;
}

function buildResearchRunningArtifact(): AnalysisArtifact {
  const artifact = buildFollowUpRunningArtifact();
  artifact.events = artifact.events.map((event) =>
    event.id === "event-follow-up-queued"
      ? {
          ...event,
          metadata: {
            mode: "research",
            anchor_id: "anchor-research-1",
          },
        }
      : event,
  );
  return artifact;
}

function buildResearchCommentArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  const anchor: ArtifactThread["anchor"] = {
    id: "anchor-research-1",
    block_id: "block-2",
    start_offset: 4,
    end_offset: 89,
    quote: "strongest value of this draft is that it turns vague editorial instincts into a review workflow",
    match_kind: "source",
    segments: [{ block_id: "block-2", start_offset: 4, end_offset: 89 }],
  };
  artifact.anchors = [...artifact.anchors, anchor];
  artifact.threads = [
    ...artifact.threads,
    {
      anchor,
      comments: [
        {
          id: "comment-research-1",
          artifact_id: artifact.artifact_id,
          anchor_id: "anchor-research-1",
          author_type: "agent",
          author_label: "research agent",
          category: "research",
          body: "This finding could use a sharper follow-up question.",
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

function buildArtifactWithDiffReview(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact) as AnalysisArtifact & Record<string, unknown>;
  artifact.diff_review = {
    mode: "surgical",
    source_revision_id: artifact.document?.revision_id ?? "revision-demo-current",
    original_markdown: artifact.document?.raw_content ?? "",
    candidate_markdown: [
      "Editorial teams need a fast way to decide whether a post is original, useful, and worth reader attention.",
      "",
      "Promote this framing into the introduction.",
      "",
      "## Inline Markdown Example",
      "",
      "This paragraph uses **bold** and *italic* emphasis.",
      "",
      "```ts",
      "const verdict = 'worth revising';",
      "```",
    ].join("\n"),
    diff_items: [
      {
        id: "diff-1",
        change_type: "replace",
        original_start_line: 3,
        original_end_line: 5,
        candidate_start_line: 3,
        candidate_end_line: 5,
        before_text:
          "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
        after_text: "Promote this framing into the introduction.",
        decision: "pending",
      },
    ],
  };
  artifact.revised_document = {
    mode: "surgical",
    source_revision_id: artifact.document?.revision_id ?? "revision-demo-current",
    markdown: artifact.diff_review!.candidate_markdown,
    accepted_comment_ids: ["comment-2"],
    generated_at: new Date().toISOString(),
  };
  return artifact;
}

function buildArtifactWithRewriteDiffReview(): AnalysisArtifact {
  const artifact = buildArtifactWithDiffReview();
  artifact.diff_review = {
    ...artifact.diff_review!,
    mode: "rewrite",
    direction_prompt: "Lead with the strongest finding.",
  };
  artifact.revised_document = {
    ...artifact.revised_document!,
    mode: "rewrite",
    direction_prompt: "Lead with the strongest finding.",
  };
  return artifact;
}

function buildArtifactWithReviewedDiffs(): AnalysisArtifact {
  const artifact = buildArtifactWithDiffReview();
  artifact.diff_review = {
    ...artifact.diff_review!,
    diff_items: [
      {
        id: "diff-1",
        change_type: "replace",
        original_start_line: 3,
        original_end_line: 5,
        candidate_start_line: 3,
        candidate_end_line: 5,
        before_text:
          "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
        after_text: "Promote this framing into the introduction.",
        decision: "accepted",
      },
    ],
  };
  return artifact;
}

function buildArtifactWithPartialReviewedDiffs(): AnalysisArtifact {
  const artifact = buildArtifactWithDiffReview();
  artifact.diff_review = {
    ...artifact.diff_review!,
    diff_items: [
      {
        id: "diff-1",
        change_type: "replace",
        original_start_line: 3,
        original_end_line: 5,
        candidate_start_line: 3,
        candidate_end_line: 5,
        before_text:
          "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
        after_text: "Promote this framing into the introduction.",
        decision: "pending",
      },
      {
        id: "diff-2",
        change_type: "insert",
        original_start_line: 8,
        original_end_line: 8,
        candidate_start_line: 8,
        candidate_end_line: 9,
        before_text: "",
        after_text: "Add a follow-up example that stays grounded in the article's core argument.",
        decision: "pending",
      },
    ],
  };
  return artifact;
}

function buildArtifactWithAcceptedAndPendingDiffs(): AnalysisArtifact {
  const artifact = buildArtifactWithDiffReview();
  artifact.diff_review = {
    ...artifact.diff_review!,
    diff_items: [
      {
        id: "diff-1",
        change_type: "replace",
        original_start_line: 3,
        original_end_line: 5,
        candidate_start_line: 3,
        candidate_end_line: 5,
        before_text:
          "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
        after_text: "Promote this framing into the introduction.",
        decision: "accepted",
      },
      {
        id: "diff-2",
        change_type: "insert",
        original_start_line: 8,
        original_end_line: 8,
        candidate_start_line: 8,
        candidate_end_line: 9,
        before_text: "",
        after_text: "Add a follow-up example that stays grounded in the article's core argument.",
        decision: "pending",
      },
    ],
  };
  return artifact;
}

function buildArtifactWithRejectedDiffs(): AnalysisArtifact {
  const artifact = buildArtifactWithDiffReview();
  artifact.diff_review = {
    ...artifact.diff_review!,
    diff_items: [
      {
        id: "diff-1",
        change_type: "replace",
        original_start_line: 3,
        original_end_line: 5,
        candidate_start_line: 3,
        candidate_end_line: 5,
        before_text:
          "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
        after_text: "Promote this framing into the introduction.",
        decision: "rejected",
      },
    ],
  };
  return artifact;
}

function buildArtifactWithRejectedRewriteDiffs(): AnalysisArtifact {
  const artifact = buildArtifactWithRewriteDiffReview();
  artifact.diff_review = {
    ...artifact.diff_review!,
    diff_items: [
      {
        id: "diff-1",
        change_type: "replace",
        original_start_line: 3,
        original_end_line: 5,
        candidate_start_line: 3,
        candidate_end_line: 5,
        before_text:
          "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
        after_text: "Promote this framing into the introduction.",
        decision: "rejected",
      },
    ],
  };
  return artifact;
}

function buildArtifactWithWordLevelDiffReview(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact) as AnalysisArtifact & Record<string, unknown>;
  const updatedSentence =
    "The strongest value of this draft is that it turns editorial instincts into a concrete review workflow with review signals.";
  artifact.diff_review = {
    mode: "surgical",
    source_revision_id: artifact.document?.revision_id ?? "revision-demo-current",
    original_markdown: artifact.document?.raw_content ?? "",
    candidate_markdown: (artifact.document?.raw_content ?? "").replace(
      "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
      updatedSentence,
    ),
    diff_items: [
      {
        id: "diff-word",
        change_type: "replace",
        original_start_line: 3,
        original_end_line: 3,
        candidate_start_line: 3,
        candidate_end_line: 3,
        before_text:
          "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
        after_text: updatedSentence,
        decision: "pending",
      },
    ],
  };
  artifact.revised_document = {
    mode: "surgical",
    source_revision_id: artifact.document?.revision_id ?? "revision-demo-current",
    markdown: artifact.diff_review!.candidate_markdown,
    accepted_comment_ids: ["comment-2"],
    generated_at: new Date().toISOString(),
  };
  return artifact as AnalysisArtifact;
}

function buildArtifactAfterAppliedRevision(): AnalysisArtifact {
  const artifact = buildArtifactWithReviewedDiffs() as AnalysisArtifact & Record<string, unknown>;
  artifact.document = {
    ...artifact.document!,
    revision_id: "revision-demo-next",
    raw_content: [
      "Editorial teams need a fast way to decide whether a post is original, useful, and worth reader attention.",
      "",
      "Promote this framing into the introduction.",
      "",
      "## Inline Markdown Example",
      "",
      "This paragraph uses **bold** and *italic* emphasis.",
      "",
      "```ts",
      "const verdict = 'worth revising';",
      "```",
    ].join("\n"),
  };
  artifact.agent_plan = [];
  artifact.agent_results = [
    {
      ...artifact.agent_results[0],
      document_revision_id: "revision-demo-current",
      findings: artifact.agent_results[0].findings.map((finding) => ({
        ...finding,
        document_revision_id: "revision-demo-current",
      })),
      metadata: {
        ...artifact.agent_results[0].metadata,
        historical: true,
      },
    },
  ];
  artifact.anchors = [
    {
      ...artifact.anchors[0],
      document_revision_id: "revision-demo-current",
    },
  ];
  artifact.threads = [
    {
      ...artifact.threads[0],
      document_revision_id: "revision-demo-current",
      anchor: {
        ...artifact.threads[0].anchor,
        document_revision_id: "revision-demo-current",
      },
      comments: artifact.threads[0].comments
        .filter((comment) => comment.category === "fact_check")
        .map((comment) => ({
          ...comment,
          document_revision_id: "revision-demo-current",
        })),
    },
  ];
  artifact.summary = null;
  artifact.review_summary = null;
  artifact.previous_draft_snapshot = {
    document_revision_id: "revision-demo-current",
    document: {
      ...mockArtifact.document!,
      revision_id: "revision-demo-current",
    },
    anchors: structuredClone(mockArtifact.anchors),
    threads: structuredClone(mockArtifact.threads),
    agent_results: structuredClone(mockArtifact.agent_results.filter((result) => result.category === "fact_check")),
    archived_at: new Date().toISOString(),
  };
  artifact.events = [
    ...artifact.events,
    {
      id: "event-revised-applied",
      artifact_id: artifact.artifact_id,
      event_type: "artifact",
      stage: "revised_markdown",
      status: "applied",
      message: "Reviewed revised markdown promoted to the working document",
      snapshot_available: true,
      created_at: new Date().toISOString(),
      metadata: {},
    },
  ];
  return artifact;
}

function buildUrlPreviewDocument(): NonNullable<AnalysisArtifact["document"]> {
  return {
    id: "preview-doc",
    revision_id: "revision-preview-doc",
    title: "Imported URL Preview",
    source_type: "url",
    source_label: "https://example.com/post",
    content_format: "markdown",
    raw_content: [
      "## Imported URL Preview",
      "",
      "A concise introduction.",
      "",
      "This section is boilerplate and can be removed.",
      "",
      "See [source reference](https://example.com/reference) for the cited material.",
    ].join("\n"),
    text: [
      "Imported URL Preview",
      "A concise introduction.",
      "This section is boilerplate and can be removed.",
      "See source reference for the cited material.",
    ].join("\n\n"),
    blocks: [
      {
        id: "url-block-1",
        index: 0,
        text: "Imported URL Preview",
        kind: "heading",
        origin: "source",
        markdown: "## Imported URL Preview",
        level: 2,
        marks: [],
      },
      {
        id: "url-block-2",
        index: 1,
        text: "A concise introduction.",
        kind: "paragraph",
        origin: "source",
        markdown: "A concise introduction.",
        marks: [],
      },
      {
        id: "url-block-3",
        index: 2,
        text: "This section is boilerplate and can be removed.",
        kind: "paragraph",
        origin: "source",
        markdown: "This section is boilerplate and can be removed.",
        marks: [],
      },
      {
        id: "url-block-4",
        index: 3,
        text: "See source reference for the cited material.",
        kind: "paragraph",
        origin: "source",
        markdown: "See [source reference](https://example.com/reference) for the cited material.",
        marks: [
          {
            start_offset: 4,
            end_offset: 20,
            kind: "link",
            href: "https://example.com/reference",
          },
        ],
      },
    ],
  };
}

function buildLinkArtifact(): AnalysisArtifact {
  const artifact = structuredClone(mockArtifact);
  artifact.document = {
    ...artifact.document!,
    text: "See source reference for the cited material.",
    blocks: [
      {
        id: "block-link",
        index: 0,
        text: "See source reference for the cited material.",
        kind: "paragraph",
        origin: "source",
        markdown: "See [source reference](https://example.com/reference) for the cited material.",
        marks: [
          {
            start_offset: 4,
            end_offset: 20,
            kind: "link",
            href: "https://example.com/reference",
          },
        ],
      },
    ],
  };
  artifact.anchors = [];
  artifact.threads = [];
  return artifact;
}

function buildLinkedHighlightArtifact(): AnalysisArtifact {
  const artifact = buildLinkArtifact();
  artifact.anchors = [
    {
      id: "anchor-link-span",
      block_id: "block-link",
      start_offset: 0,
      end_offset: artifact.document!.blocks[0]!.text.length,
      quote: artifact.document!.blocks[0]!.text,
    },
  ];
  return artifact;
}
