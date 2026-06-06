import { test, expect } from "./fixtures";

// PR 4c — ProactiveFindingsPanel on the Overview screen.
//
// The live stack's scan loop is disabled by default
// (`DASHBOARD_PROACTIVE_SCAN_ENABLED=false`), so this spec stubs the
// /api/status response to inject one finding and asserts that the panel
// renders with the citation link navigating to /errors/:id.
//
// Two viewports (default + mobile) — matches the project's existing E2E
// convention for cross-device coverage of new UI surfaces.

const STUBBED_STATUS = {
  as_of: "2026-06-06T12:00:00Z",
  apps: [
    {
      name: "shared-data-api",
      status: "ok",
      file_present: true,
      last_seen_at: "2026-06-06T11:59:55Z",
      counts_1h: { info: 5, warn: 0, error: 0 },
      counts_24h: { info: 5, warn: 0, error: 0 },
      counts_7d: { info: 5, warn: 0, error: 0 },
    },
    {
      name: "fnol",
      status: "degraded",
      file_present: true,
      last_seen_at: "2026-06-06T11:59:55Z",
      counts_1h: { info: 0, warn: 2, error: 3 },
      counts_24h: { info: 0, warn: 2, error: 3 },
      counts_7d: { info: 0, warn: 2, error: 3 },
    },
    {
      name: "customer-portal",
      status: "ok",
      file_present: true,
      last_seen_at: "2026-06-06T11:59:55Z",
      counts_1h: { info: 5, warn: 0, error: 0 },
      counts_24h: { info: 5, warn: 0, error: 0 },
      counts_7d: { info: 5, warn: 0, error: 0 },
    },
    {
      name: "agent-portal",
      status: "ok",
      file_present: true,
      last_seen_at: "2026-06-06T11:59:55Z",
      counts_1h: { info: 5, warn: 0, error: 0 },
      counts_24h: { info: 5, warn: 0, error: 0 },
      counts_7d: { info: 5, warn: 0, error: 0 },
    },
  ],
  corpus_empty: false,
  scan_enabled: true,
  last_scan_at: "2026-06-06T12:00:00Z",
  next_scan_at: "2026-06-06T12:15:00Z",
  proactive_findings: [
    {
      id: "proactive:e2e-1",
      scan_started_at: "2026-06-06T11:59:55Z",
      scan_completed_at: "2026-06-06T12:00:00Z",
      summary: "ERROR cluster in fnol — 3 chaos_honored entries in the last 10 minutes.",
      severity: "error",
      citations: [
        {
          id: "fnol:0123456789abcdef",
          timestamp: "2026-06-06T11:59:55Z",
          level: "ERROR",
          app: "fnol",
          event: "chaos_honored",
          raw: "directive=error:500 status=500",
          score: 0.91,
        },
      ],
      dry_run: false,
    },
  ],
};

test.describe("Overview proactive findings panel (7e PR 4c)", () => {
  for (const viewport of [
    { name: "desktop", width: 1280, height: 720 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    test(`renders the panel and citation link on ${viewport.name}`, async ({
      loggedInPage: page,
    }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      // Intercept /api/status BEFORE navigating so the polled refresh hits the stub.
      await page.route("**/api/status", async (route) => {
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(STUBBED_STATUS),
        });
      });

      await page.goto("/");

      const panel = page.getByTestId("proactive-findings-panel");
      await expect(panel).toBeVisible();
      const finding = page.getByTestId("proactive-finding");
      await expect(finding).toHaveCount(1);
      await expect(finding.first()).toContainText(/ERROR cluster in fnol/);
      const pill = page.getByTestId("severity-pill");
      await expect(pill.first()).toHaveText(/error/i);
      const link = page.getByTestId("proactive-citation-link").first();
      await expect(link).toHaveAttribute("href", "/errors/fnol:0123456789abcdef");
    });
  }
});
