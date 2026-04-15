import { expect, test } from "@playwright/test";

import { waitForWorkbenchReady } from "./helpers";

test("previews a .txt upload in the intake shell", async ({ page }) => {
  await waitForWorkbenchReady(page);

  await page.getByTestId("source-type-select").selectOption("file");
  await page.getByTestId("draft-file-input").setInputFiles({
    name: "preview.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Alpha paragraph.\n\nBeta paragraph."),
  });

  await page.getByTestId("preview-file-button").click();

  await expect(page.getByTestId("run-status")).toContainText("Previewed preview.txt", { timeout: 10_000 });
  await expect(page.getByTestId("intake-preview-shell")).toBeVisible();
  await expect(page.getByTestId("document-block-0")).toContainText("Alpha paragraph.");
  await expect(page.getByTestId("document-block-1")).toContainText("Beta paragraph.");
});

test("previews a markdown upload with heading-aware rendering", async ({ page }) => {
  await waitForWorkbenchReady(page);

  await page.getByTestId("source-type-select").selectOption("file");
  await page.getByTestId("draft-file-input").setInputFiles({
    name: "preview.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Preview Heading\n\nBody paragraph."),
  });

  await page.getByTestId("preview-file-button").click();

  await expect(page.getByTestId("intake-preview-shell")).toBeVisible();
  await expect(page.getByTestId("document-title")).toHaveText("Preview Heading");
  await expect(page.getByTestId("document-block-1")).toContainText("Body paragraph.");
});

test("analyzes a previewed upload without prompting to replace the draft", async ({ page }) => {
  await waitForWorkbenchReady(page);

  let dialogSeen = false;
  page.on("dialog", async (dialog) => {
    dialogSeen = true;
    await dialog.dismiss();
  });

  await page.getByTestId("source-type-select").selectOption("file");
  await page.getByTestId("draft-file-input").setInputFiles({
    name: "preview-run.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Preview Run\n\nThis draft should analyze after preview."),
  });

  await page.getByTestId("preview-file-button").click();
  await expect(page.getByTestId("run-status")).toContainText("Previewed preview-run.md", { timeout: 10_000 });

  await page.getByTestId("analyze-button").click();

  await expect(page.getByTestId("run-status")).toContainText("Run completed", { timeout: 15_000 });
  await expect(page.getByText("Overall score")).toBeVisible();
  expect(dialogSeen).toBe(false);
});

test("clears a stale file preview when a different upload is selected", async ({ page }) => {
  await waitForWorkbenchReady(page);

  await page.getByTestId("source-type-select").selectOption("file");
  await page.getByTestId("draft-file-input").setInputFiles({
    name: "first.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("First preview body."),
  });

  await page.getByTestId("preview-file-button").click();
  await expect(page.getByTestId("intake-preview-shell")).toBeVisible();
  await expect(page.getByTestId("document-block-0")).toContainText("First preview body.");

  await page.getByTestId("draft-file-input").setInputFiles({
    name: "second.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Second preview body."),
  });

  await expect(page.getByTestId("intake-preview-shell")).toBeHidden();
  await expect(page.getByTestId("document-block-0")).toBeHidden();
  await expect(page.getByText("second.txt")).toBeVisible();
});
