import { expect, test } from "@playwright/test";

test("rejects unsupported file uploads", async ({ page }) => {
  await page.goto("/");

  await page.getByTestId("source-type-select").selectOption("file");
  await page.getByTestId("draft-file-input").setInputFiles({
    name: "notes.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("not a valid text upload"),
  });
  await page.getByTestId("analyze-button").click();

  await expect(page.getByTestId("run-status")).toContainText("Request failed with status 415", {
    timeout: 10_000,
  });
});
