import { test, expect } from "./fixtures";

test.describe("Log Explorer — semantic search (7d)", () => {
  test("typing a query switches the table to search mode with a score column", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/logs");
    await expect(
      page.getByRole("heading", { name: /log explorer/i }),
    ).toBeVisible();

    // Wait for the initial /api/logs render so we know we're in tail mode.
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("score-header")).toHaveCount(0);

    // Type a query. Backend is embeddings-disabled (no OPENAI_API_KEY in
    // local .env by default) → the UI surfaces the 503 as a friendly alert.
    // Backend embeddings-enabled (operator set the key) → score column renders.
    await page.getByTestId("filter-query").fill("auth failures");

    await Promise.race([
      page.getByTestId("score-header").waitFor({ timeout: 4000 }),
      page
        .getByRole("alert")
        .filter({ hasText: /OPENAI_API_KEY/ })
        .waitFor({ timeout: 4000 }),
    ]);

    // Pagination's "Load more" must NOT appear in search mode.
    await expect(page.getByTestId("load-more")).toHaveCount(0);
  });

  test("clearing the query restores cursor-mode pagination", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/logs");
    await page.waitForLoadState("networkidle");

    await page.getByTestId("filter-query").fill("anything");
    // Wait for ANY response — either score header or alert — before clearing,
    // so we know the search request fired.
    await Promise.race([
      page.getByTestId("score-header").waitFor({ timeout: 4000 }),
      page.getByRole("alert").first().waitFor({ timeout: 4000 }),
    ]);

    await page.getByTestId("filter-query").fill("");
    await page.waitForLoadState("networkidle");

    // Back to substring mode — score column absent.
    await expect(page.getByTestId("score-header")).toHaveCount(0);
    // First row should reappear (assuming the live stack has > 0 log lines).
    await expect(page.getByTestId("log-row").first()).toBeVisible();
  });
});
