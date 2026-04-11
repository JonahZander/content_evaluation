import { fireEvent, render, screen } from "@testing-library/react";

import { DocumentPane } from "@/components/review/DocumentPane";
import type { ArtifactAnchor, ArtifactDocument, ArtifactThread } from "@/lib/types";

function buildDocument(overrides: Partial<ArtifactDocument> = {}): ArtifactDocument {
  return {
    id: "doc-list",
    revision_id: "revision-list",
    title: "Markdown list draft",
    source_type: "text",
    source_label: "Draft",
    content_format: "markdown",
    raw_content: "- Alpha first item\n- Beta second item",
    text: "Alpha first item\nBeta second item",
    blocks: [
      {
        id: "block-list",
        index: 0,
        text: "Alpha first item\nBeta second item",
        kind: "list",
        origin: "source",
        markdown: "- Alpha first item\n- Beta second item",
        list_items: [
          { text: "Alpha first item", start_offset: 0, end_offset: 16 },
          { text: "Beta second item", start_offset: 17, end_offset: 33 },
        ],
        ordered: false,
        marks: [],
      },
    ],
    ...overrides,
  };
}

function buildProps({
  document = buildDocument(),
  anchors = [],
  threads = [],
  onSelectionDraft = vi.fn(),
}: {
  document?: ArtifactDocument | null;
  anchors?: ArtifactAnchor[];
  threads?: ArtifactThread[];
  onSelectionDraft?: ReturnType<typeof vi.fn>;
} = {}) {
  return {
    document,
    anchors,
    threads,
    anchorThreadMap: new Map(anchors.map((anchor) => [anchor.id, { colors: ["#cc5500"] }])),
    activeDocumentRevisionId: document?.revision_id ?? null,
    selectionEnabled: true,
    hoveredAnchorId: null,
    hiddenBlockIds: [],
    previewPruningEnabled: false,
    anchorRefs: { current: {} },
    commentRefs: { current: {} },
    onHoverAnchor: vi.fn(),
    onSelectionDraft,
    onHideBlock: vi.fn(),
    onRestoreBlock: vi.fn(),
    onRestoreAllBlocks: vi.fn(),
    replyDrafts: {},
    activeReplyComposerId: null,
    editingCommentId: null,
    editingBody: "",
    onReplyDraftChange: vi.fn(),
    onToggleReplyComposer: vi.fn(),
    onAddReply: vi.fn(),
    onDeleteReply: vi.fn(),
    onReviewState: vi.fn(),
    onStartEditing: vi.fn(),
    onEditingBodyChange: vi.fn(),
    onSaveEdit: vi.fn(),
    onCancelEdit: vi.fn(),
    onDeleteComment: vi.fn(),
    threadActionLocalError: { commentId: null, message: null },
  };
}

function setDomSelection(startNode: Node, startOffset: number, endNode: Node, endOffset: number) {
  const selection = window.getSelection();
  if (!selection) {
    throw new Error("Selection API unavailable in test environment.");
  }
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  selection.removeAllRanges();
  selection.addRange(range);
}

afterEach(() => {
  window.getSelection()?.removeAllRanges();
});

describe("DocumentPane list blocks", () => {
  it("renders unordered list blocks as one semantic list with inline marks", () => {
    const document = buildDocument({
      raw_content: "- Alpha **bold** item\n- Beta [source](https://example.com/source)",
      text: "Alpha bold item\nBeta source",
      blocks: [
        {
          id: "block-list",
          index: 0,
          text: "Alpha bold item\nBeta source",
          kind: "list",
          origin: "source",
          markdown: "- Alpha **bold** item\n- Beta [source](https://example.com/source)",
          list_items: [
            { text: "Alpha bold item", start_offset: 0, end_offset: 15 },
            { text: "Beta source", start_offset: 16, end_offset: 27 },
          ],
          ordered: false,
          marks: [
            { start_offset: 6, end_offset: 10, kind: "strong" },
            { start_offset: 21, end_offset: 27, kind: "link", href: "https://example.com/source" },
          ],
        },
      ],
    });

    const { container } = render(<DocumentPane {...buildProps({ document })} />);

    const list = container.querySelector("ul");
    expect(list).not.toBeNull();
    expect(list?.querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByRole("link", { name: "source" })).toHaveAttribute("href", "https://example.com/source");
  });

  it("renders ordered list blocks with the authored starting number", () => {
    const document = buildDocument({
      raw_content: "3. Third item\n4. Fourth item",
      text: "Third item\nFourth item",
      blocks: [
        {
          id: "block-list",
          index: 0,
          text: "Third item\nFourth item",
          kind: "list",
          origin: "source",
          markdown: "3. Third item\n4. Fourth item",
          list_items: [
            { text: "Third item", start_offset: 0, end_offset: 10 },
            { text: "Fourth item", start_offset: 11, end_offset: 22 },
          ],
          ordered: true,
          start_number: 3,
          marks: [],
        },
      ],
    });

    const { container } = render(<DocumentPane {...buildProps({ document })} />);

    const list = container.querySelector("ol");
    expect(list).not.toBeNull();
    expect(list).toHaveAttribute("start", "3");
    expect(list?.querySelectorAll("li")).toHaveLength(2);
  });

  it("renders one thread card for list anchors that continue across multiple items", () => {
    const anchor: ArtifactAnchor = {
      id: "anchor-list",
      document_revision_id: "revision-list",
      block_id: "block-list",
      start_offset: 6,
      end_offset: 25,
      quote: "first item\nBeta seco",
      match_kind: "source",
      segments: [
        { block_id: "block-list", start_offset: 6, end_offset: 16 },
        { block_id: "block-list", start_offset: 17, end_offset: 25 },
      ],
    };
    const threads: ArtifactThread[] = [
      {
        document_revision_id: "revision-list",
        anchor,
        comments: [
          {
            id: "comment-list",
            artifact_id: "artifact-list",
            anchor_id: "anchor-list",
            document_revision_id: "revision-list",
            author_type: "agent",
            author_label: "Editorial agent",
            category: "editorial",
            body: "This sequence should stay grouped inside one list row.",
            review_state: "unreviewed",
            created_at: "2026-04-11T00:00:00.000Z",
            updated_at: "2026-04-11T00:00:00.000Z",
            replies: [],
          },
        ],
      },
    ];

    const { container } = render(<DocumentPane {...buildProps({ anchors: [anchor], threads })} />);

    expect(screen.getByTestId("thread-anchor-list")).toBeInTheDocument();
    expect(screen.getAllByTestId("comment-comment-list")).toHaveLength(1);
    expect(container.querySelectorAll('[data-anchor-ids="anchor-list"]')).toHaveLength(2);
  });

  it("maps single-item selections back to block-local offsets and ignores cross-item selections", () => {
    const onSelectionDraft = vi.fn();
    render(<DocumentPane {...buildProps({ onSelectionDraft })} />);

    const firstItem = screen.getByText("Alpha first item");
    const secondItem = screen.getByText("Beta second item");
    const firstTextNode = firstItem.firstChild;
    const secondTextNode = secondItem.firstChild;
    if (!(firstTextNode instanceof Text) || !(secondTextNode instanceof Text)) {
      throw new Error("Expected plain text nodes inside rendered list items.");
    }

    setDomSelection(firstTextNode, 6, firstTextNode, 11);
    fireEvent.mouseUp(firstItem);

    expect(onSelectionDraft).toHaveBeenLastCalledWith({
      blockId: "block-list",
      startOffset: 6,
      endOffset: 11,
      quote: "first",
    });

    setDomSelection(firstTextNode, 6, secondTextNode, 4);
    fireEvent.mouseUp(secondItem);

    expect(onSelectionDraft).toHaveBeenLastCalledWith(null);
  });
});
