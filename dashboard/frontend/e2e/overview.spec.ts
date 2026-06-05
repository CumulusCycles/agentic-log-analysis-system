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
});
