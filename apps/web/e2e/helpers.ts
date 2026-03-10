import { expect, type Locator, type Page } from "@playwright/test";

export async function submitDraft(page: Page, title: string, text: string): Promise<void> {
  await page.goto("/");
  await page.getByTestId("draft-title-input").fill(title);
  await page.getByTestId("draft-text-input").fill(text);
  await page.getByTestId("analyze-button").click();
  await expect(page.getByTestId("run-status")).toContainText("Run completed", {
    timeout: 15_000,
  });
}

export async function expectRunLoaded(page: Page, title: string): Promise<void> {
  await expect(page.getByRole("heading", { name: title })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("connector-canvas")).toBeVisible();
  await expect(page.locator("[data-testid^='thread-anchor-']")).toHaveCount(5, {
    timeout: 15_000,
  });
}

export async function selectText(block: Locator, startOffset: number, endOffset: number): Promise<void> {
  await block.evaluate(
    (element, offsets) => {
      const paragraph = element as HTMLParagraphElement;
      const { startOffset, endOffset } = offsets;
      const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
      const textNodes: Text[] = [];
      let currentNode = walker.nextNode();
      while (currentNode !== null) {
        textNodes.push(currentNode as Text);
        currentNode = walker.nextNode();
      }
      if (textNodes.length === 0) {
        throw new Error("Expected the paragraph to contain text nodes");
      }

      function resolveTextPosition(offset: number): [Text, number] {
        let remaining = offset;
        for (const textNode of textNodes) {
          const nodeLength = textNode.textContent?.length ?? 0;
          if (remaining <= nodeLength) {
            return [textNode, remaining];
          }
          remaining -= nodeLength;
        }
        const lastNode = textNodes[textNodes.length - 1];
        return [lastNode, lastNode.textContent?.length ?? 0];
      }

      const selection = window.getSelection();
      if (selection === null) {
        throw new Error("Selection API is not available");
      }

      const range = document.createRange();
      const [startNode, startNodeOffset] = resolveTextPosition(startOffset);
      const [endNode, endNodeOffset] = resolveTextPosition(endOffset);
      range.setStart(startNode, startNodeOffset);
      range.setEnd(endNode, endNodeOffset);
      selection.removeAllRanges();
      selection.addRange(range);
      paragraph.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    },
    { startOffset, endOffset },
  );
}
