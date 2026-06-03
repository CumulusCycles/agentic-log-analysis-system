import { expect, test } from "./fixtures";

test.describe("Claim detail page", () => {
  test("detail view renders the claim and status history timeline", async ({
    loggedInPage: page,
  }) => {
    // Walk through the list to grab a real seeded claim id.
    await page.goto("/claims");
    const firstRow = page.getByTestId("claims-list").locator("a").first();
    await expect(firstRow).toBeVisible();
    await firstRow.click();
    await expect(page).toHaveURL(/\/claims\/[^/]+$/);

    // Status timeline is always present — SDA seeds at least one row of
    // claim_status_history per claim (the initial CREATED transition).
    await expect(page.getByTestId("status-timeline")).toBeVisible();
    await expect(page.getByTestId("status-badge")).toBeVisible();
  });

  test("anonymous /claims/some-id redirects to /login", async ({ page }) => {
    await page.goto("/claims/anything");
    await expect(page).toHaveURL(/\/login$/);
  });
});
