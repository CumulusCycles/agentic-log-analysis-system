import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";
import { config as loadEnv } from "dotenv";

// Load the repo-root .env so TEST_AGENT_USERNAME (and any other
// playwright-relevant overrides) reach process.env before fixtures
// resolve. Playwright is launched from `apps/agent-portal/frontend/`,
// three levels below the .env file. Missing .env is harmless —
// `loadEnv` returns without erroring and fixtures fall back to defaults.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
loadEnv({ path: path.resolve(__dirname, "../../../.env") });

// Playwright runs against a LIVE stack — `docker compose up -d` first.
// The agent-portal container exposes host port 8081.
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8081";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // single-stack — avoid race on shared seed data
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Tag every E2E request so the dashboard ingest gate drops it from
    // Chroma — see docs/decisions/ADR-011-x-source-header-convention.md.
    extraHTTPHeaders: { "X-Source": "test" },
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-safari",
      use: { ...devices["iPhone 14"] },
    },
  ],
});
