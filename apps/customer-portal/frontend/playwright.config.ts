import { defineConfig, devices } from "@playwright/test";

// Playwright runs against a LIVE stack — `docker compose up -d` first.
// The customer-portal container exposes host port 3001.
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3001";

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
