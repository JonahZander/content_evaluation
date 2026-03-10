import { fireEvent, render, screen } from "@testing-library/react";

import { ReviewWorkbench } from "@/components/ReviewWorkbench";
import { mockRunDetail } from "@/lib/mock-data";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({
  createRun: vi.fn(),
  createRunFromFile: vi.fn(),
  fetchRun: vi.fn(),
  createComment: vi.fn().mockResolvedValue(undefined),
  addReply: vi.fn().mockResolvedValue(undefined),
  updateReviewState: vi.fn().mockResolvedValue(undefined),
  updateHumanComment: vi.fn().mockResolvedValue(undefined),
  deleteHumanComment: vi.fn().mockResolvedValue(undefined),
  getExportUrl: vi.fn(() => "http://localhost:8000/export"),
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
  vi.mocked(api.fetchRun).mockResolvedValue(mockRunDetail);
});

describe("ReviewWorkbench", () => {
  it("renders text, threads, and connector paths", () => {
    render(<ReviewWorkbench initialRun={mockRunDetail} />);

    expect(screen.getByText("How Editorial Teams Can Evaluate AI-Written Posts")).toBeInTheDocument();
    expect(screen.getByTestId("thread-anchor-2")).toBeInTheDocument();
    expect(screen.getByTestId("connector-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("connector-comment-2")).toBeInTheDocument();
  });

  it("shows review buttons and reply controls", () => {
    render(<ReviewWorkbench initialRun={mockRunDetail} />);

    expect(screen.getAllByRole("button", { name: "Accept" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Reject" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Uncertain" }).length).toBeGreaterThan(0);
    expect(screen.getAllByPlaceholderText("Reply to this comment").length).toBeGreaterThan(0);
  });

  it("opens export URLs", () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<ReviewWorkbench initialRun={mockRunDetail} />);

    fireEvent.click(screen.getByRole("button", { name: "Export Markdown" }));
    expect(openSpy).toHaveBeenCalled();
    openSpy.mockRestore();
  });
});
