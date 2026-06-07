import { test, expect } from "./fixtures";

test.describe("Overview screen (7c)", () => {
  test("renders the Overview heading and four app cards", async ({ loggedInPage: page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /^overview$/i })).toBeVisible();
    const cards = page.getByTestId("status-card");
    await expect(cards).toHaveCount(4);
    await expect(cards.filter({ has: page.getByText("shared-data-api") })).toHaveCount(1);
    await expect(cards.filter({ has: page.getByText("agent-portal") })).toHaveCount(1);
  });

  test("each card shows a status badge with one of ok / degraded / error", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/");
    const badges = page.getByTestId("status-badge");
    await expect(badges).toHaveCount(4);
    const values = await badges.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-status")),
    );
    for (const v of values) {
      expect(["ok", "degraded", "error"]).toContain(v);
    }
  });

  test("clicking the shared-data-api card drills down to /logs?app=shared-data-api", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/");
    await page.getByTestId("status-card").filter({ hasText: "shared-data-api" }).click();
    await expect(page).toHaveURL(/\/logs\?app=shared-data-api/);
    await expect(page.getByRole("heading", { name: /log explorer/i })).toBeVisible();
  });

  test("renders the trend-window selector with 1h/24h/7d radios", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/");
    const selector = page.getByTestId("history-window-selector");
    await expect(selector).toBeVisible();
    await expect(page.getByTestId("history-window-1h")).toBeVisible();
    await expect(page.getByTestId("history-window-24h")).toBeVisible();
    await expect(page.getByTestId("history-window-7d")).toBeVisible();
    // 24h is the default per the API contract.
    await expect(page.getByTestId("history-window-24h")).toBeChecked();
  });

  test("switching the trend window refetches /api/status/history with the new window", async ({
    loggedInPage: page,
  }) => {
    // Regex (not glob) so the route matches across query strings — see
    // `reference_playwright_route_patterns_query_strings`.
    let lastQuery: string | null = null;
    await page.route(/\/api\/status\/history/, async (route, request) => {
      lastQuery = new URL(request.url()).searchParams.get("window");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          as_of: "2026-06-07T00:00:00Z",
          window: lastQuery ?? "24h",
          bucket_minutes: 60,
          apps: {
            "shared-data-api": [],
            fnol: [],
            "customer-portal": [],
            "agent-portal": [],
          },
        }),
      });
    });
    await page.goto("/");
    await expect(page.getByTestId("history-window-selector")).toBeVisible();
    await expect.poll(() => lastQuery).toBe("24h");

    await page.getByTestId("history-window-1h").check();
    await expect.poll(() => lastQuery).toBe("1h");

    await page.getByTestId("history-window-7d").check();
    await expect.poll(() => lastQuery).toBe("7d");
  });
});
