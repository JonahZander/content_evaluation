import type { MutableRefObject, ReactNode } from "react";

import styles from "@/components/ReviewWorkbench.module.css";
import { colorForCategory } from "@/components/review/category-colors";
import type { NormalizedDocument, TextAnchor } from "@/lib/types";

interface AnchorThread {
  colors: string[];
}

interface SelectionDraft {
  blockId: string;
  startOffset: number;
  endOffset: number;
  quote: string;
}

interface DocumentPaneProps {
  document: NormalizedDocument | null;
  anchors: TextAnchor[];
  anchorThreadMap: Map<string, AnchorThread>;
  hoveredAnchorId: string | null;
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>;
  onHoverAnchor: (anchorId: string | null) => void;
  onSelectionDraft: (draft: SelectionDraft | null) => void;
}

function renderAnchor(
  anchor: TextAnchor,
  blockText: string,
  colors: string[],
  isHovered: boolean,
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>,
  onHoverAnchor: (anchorId: string | null) => void,
): ReactNode {
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
      tabIndex={0}
      onFocus={() => onHoverAnchor(anchor.id)}
      onBlur={() => onHoverAnchor(null)}
      onMouseEnter={() => onHoverAnchor(anchor.id)}
      onMouseLeave={() => onHoverAnchor(null)}
      style={{
        background: colors.length === 1 ? gradient : "rgba(255, 247, 236, 0.9)",
        boxShadow:
          colors.length > 1
            ? `inset 0 0 0 1px rgba(0,0,0,0.04), inset 6px 0 0 0 ${colors[0]}`
            : undefined,
        borderBottom: `2px solid ${colors[0]}`,
      }}
    >
      {blockText.slice(anchor.start_offset, anchor.end_offset)}
    </span>
  );
}

function renderParagraph(
  blockId: string,
  blockText: string,
  anchors: TextAnchor[],
  anchorThreadMap: Map<string, AnchorThread>,
  hoveredAnchorId: string | null,
  anchorRefs: MutableRefObject<Record<string, HTMLSpanElement | null>>,
  onHoverAnchor: (anchorId: string | null) => void,
): ReactNode {
  const blockAnchors = anchors
    .filter((anchor) => anchor.block_id === blockId)
    .sort((left, right) => left.start_offset - right.start_offset);

  if (blockAnchors.length === 0) {
    return blockText;
  }

  const fragments: ReactNode[] = [];
  let cursor = 0;
  blockAnchors.forEach((anchor) => {
    if (cursor < anchor.start_offset) {
      fragments.push(blockText.slice(cursor, anchor.start_offset));
    }
    const colors = anchorThreadMap.get(anchor.id)?.colors ?? [colorForCategory("human")];
    fragments.push(
      renderAnchor(anchor, blockText, colors, hoveredAnchorId === anchor.id, anchorRefs, onHoverAnchor),
    );
    cursor = anchor.end_offset;
  });
  if (cursor < blockText.length) {
    fragments.push(blockText.slice(cursor));
  }
  return fragments;
}

function resolveSelectionDraft(
  paragraph: HTMLParagraphElement,
  selection: Selection | null,
  blockId: string,
): SelectionDraft | null {
  if (selection === null || selection.rangeCount === 0 || selection.isCollapsed) {
    return null;
  }

  const range = selection.getRangeAt(0);
  if (!paragraph.contains(range.commonAncestorContainer)) {
    return null;
  }

  const selectedText = range.toString().trim();
  if (!selectedText) {
    return null;
  }

  const offsetRange = range.cloneRange();
  offsetRange.selectNodeContents(paragraph);
  offsetRange.setEnd(range.startContainer, range.startOffset);
  const startOffset = offsetRange.toString().length;

  return {
    blockId,
    startOffset,
    endOffset: startOffset + selectedText.length,
    quote: selectedText,
  };
}

export function DocumentPane({
  document,
  anchors,
  anchorThreadMap,
  hoveredAnchorId,
  anchorRefs,
  onHoverAnchor,
  onSelectionDraft,
}: DocumentPaneProps) {
  return (
    <div className={styles.documentPane}>
      <div className={styles.sectionTitle}>Text under review</div>
      <h2 className={styles.documentTitle}>{document?.title ?? "No document loaded"}</h2>
      {document?.blocks.length ? (
        document.blocks.map((block) => (
          <p
            key={block.id}
            className={styles.paragraph}
            data-block-id={block.id}
            data-testid={`document-block-${block.index}`}
            onMouseUp={(event) => {
              const draft = resolveSelectionDraft(event.currentTarget, window.getSelection(), block.id);
              onSelectionDraft(draft);
            }}
          >
            {renderParagraph(
              block.id,
              block.text,
              anchors,
              anchorThreadMap,
              hoveredAnchorId,
              anchorRefs,
              onHoverAnchor,
            )}
          </p>
        ))
      ) : (
        <div className={styles.emptyState}>Submit a URL, pasted draft, or text file to start the review.</div>
      )}
    </div>
  );
}
