import { test, expect } from "./fixtures";

test.describe("Log Explorer screen (7c)", () => {
  test("renders filter bar + table with rows from the live stack", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/logs");
    await expect(page.getByRole("heading", { name: /log explorer/i })).toBeVisible();
    // At least one log row arrives from the live volumes.
    await expect(page.getByTestId("log-row").first()).toBeVisible();
  });

  test("level=ERROR filter shows only ERROR rows (or empty state)", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/logs");
    // Untick every level except ERROR.
    await page.getByTestId("filter-level-DEBUG").uncheck();
    await page.getByTestId("filter-level-INFO").uncheck();
    await page.getByTestId("filter-level-WARN").uncheck();

    // Wait for refetch to settle.
    await page.waitForLoadState("networkidle");

    const rows = page.getByTestId("log-row");
    const count = await rows.count();
    if (count === 0) {
      await expect(page.getByText(/no entries match/i)).toBeVisible();
    } else {
      const levels = await rows.evaluateAll((els) =>
        els.map((el) => el.getAttribute("data-level")),
      );
      for (const level of levels) {
        expect(level).toBe("ERROR");
      }
    }
  });

  test("clicking a row expands its fields + raw panel", async ({ loggedInPage: page }) => {
    await page.goto("/logs");
    const firstRow = page.getByTestId("log-row").first();
    await expect(firstRow).toBeVisible();
    await firstRow.click();
    await expect(page.getByTestId("log-row-expanded").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /^raw$/i })).toBeVisible();
  });

  test("navigating to /logs?app=fnol pre-selects only the FNOL filter", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/logs?app=fnol");
    await expect(page.getByTestId("filter-app-fnol")).toBeChecked();
    await expect(page.getByTestId("filter-app-shared-data-api")).not.toBeChecked();
    await expect(page.getByTestId("filter-app-customer-portal")).not.toBeChecked();
    await expect(page.getByTestId("filter-app-agent-portal")).not.toBeChecked();

    await page.waitForLoadState("networkidle");
    const rows = page.getByTestId("log-row");
    const count = await rows.count();
    if (count > 0) {
      const apps = await rows.evaluateAll((els) => els.map((el) => el.getAttribute("data-app")));
      for (const app of apps) expect(app).toBe("fnol");
    }
  });
});
