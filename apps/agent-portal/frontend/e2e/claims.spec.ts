import { expect, test } from "./fixtures";

test.describe("Claims page", () => {
  test("renders the claims heading and at least one seeded claim", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/claims");
    await expect(
      page.getByRole("heading", { name: /all claims/i }),
    ).toBeVisible();

    // SDA seed always creates ~10 claims, so the list must render at least one
    // status badge.
    await expect(page.getByTestId("status-badge").first()).toBeVisible();
  });

  test("clicking a claim row navigates to the detail page", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/claims");
    const firstRow = page.getByTestId("claims-list").locator("a").first();
    await expect(firstRow).toBeVisible();
    await firstRow.click();
    await expect(page).toHaveURL(/\/claims\/[^/]+$/);
  });

  test("anonymous /claims redirects to /login", async ({ page }) => {
    await page.goto("/claims");
    await expect(page).toHaveURL(/\/login$/);
  });
});
