import { test, expect } from "./fixtures";

// Vectorstore Stats tab — top-nav link routes to a page that polls
// /api/chroma/stats and renders summary cards + 5 bar-chart sections.
//
// Stubs the API response so the spec is deterministic regardless of how
// much real traffic is in Chroma when the suite runs (otherwise the bar
// counts vary run-to-run). Two viewports — matches the project's existing
// pattern for new UI tabs.

const STUBBED_STATS = {
  total_count: 445,
  by_app: {
    fnol: 200,
    "shared-data-api": 170,
    "agent-portal": 40,
    "customer-portal": 35,
  },
  by_level: { WARN: 265, ERROR: 180 },
  by_source: { synthetic: 385, prod: 60 },
  by_event: [
    { event: "chaos_honored", count: 200 },
    { event: "login_failed", count: 50 },
  ],
  by_day: [
    { date: "2026-06-04", count: 0 },
    { date: "2026-06-05", count: 100 },
    { date: "2026-06-06", count: 345 },
  ],
  embedding_model: "text-embedding-3-small",
  dimensions: 1536,
  as_of: "2026-06-06T22:50:00Z",
};

test.describe("Vectorstore Stats tab", () => {
  for (const viewport of [
    { name: "desktop", width: 1280, height: 720 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    test(`renders summary cards + charts on ${viewport.name}`, async ({ loggedInPage: page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      await page.route(/\/api\/chroma\/stats/, async (route) => {
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(STUBBED_STATS),
        });
      });

      // Navigate via the top-nav link so the spec also covers routing.
      await page.goto("/");
      await page.getByRole("link", { name: "Vectorstore Stats" }).click();

      // Heading + summary cards.
      await expect(page.getByRole("heading", { name: "Vectorstore Stats" })).toBeVisible();
      await expect(page.getByText("Total embedded documents")).toBeVisible();
      await expect(page.getByText("text-embedding-3-small")).toBeVisible();

      // All five section headings. Default window is 7d.
      await expect(page.getByText("By app")).toBeVisible();
      await expect(page.getByText("By level")).toBeVisible();
      await expect(page.getByText("By source")).toBeVisible();
      await expect(page.getByText("Top events")).toBeVisible();
      await expect(page.getByText("By day (last 7 days)")).toBeVisible();

      // Sample data points from each section. Use exact-match on the
      // by_level bar so the "Only WARN + ERROR pass the ingest gate" hint
      // text doesn't collide with the bar label under strict mode.
      await expect(page.getByText("fnol")).toBeVisible();
      await expect(page.getByText("WARN", { exact: true })).toBeVisible();
      await expect(page.getByText("synthetic")).toBeVisible();
      await expect(page.getByText("chaos_honored")).toBeVisible();

      // No 503 banner.
      await expect(page.getByText(/Vectorstore is unavailable/)).toHaveCount(0);
    });
  }

  test("renders the 503 unavailable banner when /api/chroma/stats returns 503", async ({
    loggedInPage: page,
  }) => {
    await page.route(/\/api\/chroma\/stats/, async (route) => {
      await route.fulfill({
        status: 503,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ detail: "Vectorstore unavailable" }),
      });
    });

    await page.goto("/vectorstore-stats");
    await expect(page.getByRole("alert")).toContainText("Vectorstore is unavailable");
  });

  test("switching the By Day window sends since on the next /api/chroma/stats request", async ({
    loggedInPage: page,
  }) => {
    let firstQuery: string | null = null;
    let secondQuery: string | null = null;
    let callCount = 0;
    await page.route(/\/api\/chroma\/stats/, async (route, request) => {
      callCount += 1;
      if (callCount === 1) firstQuery = new URL(request.url()).search;
      if (callCount === 2) secondQuery = new URL(request.url()).search;
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(STUBBED_STATS),
      });
    });

    await page.goto("/vectorstore-stats");
    await expect(page.getByText("By day (last 7 days)")).toBeVisible();

    // The default 7d preset resolves a `since` on first request.
    expect(firstQuery).toContain("since=");

    await page.getByTestId("stats-window-1h").check();
    await expect.poll(() => secondQuery).not.toBeNull();
    // 1h preset still carries since; the value is more recent than 7d.
    expect(secondQuery!).toContain("since=");
  });
});
