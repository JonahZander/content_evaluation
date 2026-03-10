import { expect, test } from "@playwright/test";
import { waitForWorkbenchReady } from "./helpers";

test("rejects unsupported file uploads", async ({ page }) => {
  await waitForWorkbenchReady(page);

  await page.getByTestId("source-type-select").selectOption("file");
  await page.getByTestId("draft-file-input").setInputFiles({
    name: "notes.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("not a valid text upload"),
  });
  await page.getByTestId("analyze-button").click();

  await expect(page.getByTestId("run-status")).toContainText("Only .txt and .md uploads are supported", {
    timeout: 10_000,
  });
});
