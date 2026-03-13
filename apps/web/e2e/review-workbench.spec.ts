import { expect, test } from "@playwright/test";

import { expectRunLoaded, selectText, submitDraft } from "./helpers";

const draftTitle = "Playwright review draft";
const draftText = [
  "Editorial teams need a fast way to decide whether a post is original, useful, and worth reader attention.",
  "The strongest value of this draft is that it turns vague editorial instincts into a review workflow with concrete review signals.",
  "Some later sections restate the introduction without adding evidence, which weakens the pacing and makes the piece feel more generic.",
].join("\n\n");

test("submits pasted text and renders the analyzed review state", async ({ page }) => {
  await submitDraft(page, draftTitle, draftText);

  await expectRunLoaded(page, draftTitle);
  await expect(page.getByTestId("run-status")).toContainText("Run completed");
  await expect(page.getByText("Overall evaluation")).toBeVisible();
  await expect(page.getByText("Run log")).toBeVisible();
  await expect(page.locator("[data-testid^='comment-comment-']").first()).toBeVisible();
});

test("allows replying to and reviewing an agent comment", async ({ page }) => {
  await submitDraft(page, draftTitle, draftText);
  await expectRunLoaded(page, draftTitle);

  const firstComment = page.locator("[data-testid^='comment-comment-']").first();
  const commentId = await firstComment.getAttribute("data-testid");
  if (commentId === null) {
    throw new Error("Expected a comment test id");
  }
  const rawCommentId = commentId.replace("comment-", "");

  await page.getByTestId(`reply-input-${rawCommentId}`).fill("Playwright reviewer reply");
  await page.getByTestId(`reply-submit-${rawCommentId}`).click();
  await expect(firstComment.getByText("Playwright reviewer reply")).toBeVisible();

  await page.getByTestId(`review-state-${rawCommentId}-accepted`).click();
  await expect(firstComment.getByText("accepted")).toBeVisible();
});

test("creates a standalone reviewer comment from a text selection", async ({ page }) => {
  await submitDraft(page, draftTitle, draftText);
  await expectRunLoaded(page, draftTitle);

  const firstBlock = page.getByTestId("document-block-0");
  await selectText(firstBlock, 0, 16);

  await expect(page.getByText("Create a reviewer comment")).toBeVisible();
  await page.getByTestId("selection-comment-input").fill("Reviewer note created from a browser selection");
  await page.getByTestId("selection-comment-save").click();

  await expect(page.getByText("Reviewer note created from a browser selection")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit" }).last()).toBeVisible();
});

test("opens export endpoints for markdown and json", async ({ page }) => {
  await submitDraft(page, draftTitle, draftText);
  await expectRunLoaded(page, draftTitle);

  const markdownPopupPromise = page.waitForEvent("popup");
  await page.getByTestId("export-markdown-button").click();
  const markdownPopup = await markdownPopupPromise;
  await markdownPopup.waitForLoadState("domcontentloaded");
  await expect(markdownPopup).toHaveURL(/\/api\/v1\/runs\/.+\/export\.md$/);

  const jsonPopupPromise = page.waitForEvent("popup");
  await page.getByTestId("export-json-button").click();
  const jsonPopup = await jsonPopupPromise;
  await jsonPopup.waitForLoadState("domcontentloaded");
  await expect(jsonPopup).toHaveURL(/\/api\/v1\/runs\/.+\/export\.json$/);
});
