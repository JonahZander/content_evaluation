import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const repoRoot = path.resolve(__dirname, "..", "..");
const testApiPort = 8001;
const testWebPort = 3001;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["html"], ["line"]] : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${testWebPort}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        `uv run --extra dev --directory services/api uvicorn content_evaluation.api.main:app --host 127.0.0.1 --port ${testApiPort}`,
      cwd: repoRoot,
      url: `http://127.0.0.1:${testApiPort}/health`,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
      timeout: 120_000,
      env: {
        ...process.env,
        UV_CACHE_DIR: ".uv-cache",
        CONTENT_EVAL_APP_ENV: "test",
        CONTENT_EVAL_CORS_ORIGINS: `["http://127.0.0.1:${testWebPort}"]`,
        CONTENT_EVAL_OPENAI_API_KEY: "",
        CONTENT_EVAL_ANTHROPIC_API_KEY: "",
        CONTENT_EVAL_GEMINI_API_KEY: "",
        CONTENT_EVAL_TAVILY_API_KEY: "",
        CONTENT_EVAL_DATABASE_URL: "",
      },
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${testWebPort}`,
      cwd: __dirname,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE_URL: `http://127.0.0.1:${testApiPort}`,
      },
      url: `http://127.0.0.1:${testWebPort}`,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
      timeout: 120_000,
    },
  ],
});
