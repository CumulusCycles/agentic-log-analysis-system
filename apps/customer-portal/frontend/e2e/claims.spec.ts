import { expect, test } from "./fixtures";

test.describe("Claims page", () => {
  test("renders the claims heading (list may be empty)", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/claims");
    await expect(
      page.getByRole("heading", { name: /my claims/i }),
    ).toBeVisible();

    // If any claims are seeded, the status badge should be visible. If not,
    // the empty-state copy should render.
    const badge = page.getByTestId("status-badge").first();
    const empty = page.getByText(/no claims filed/i);
    await expect(badge.or(empty)).toBeVisible();
  });

  test("anonymous /claims redirects to /login", async ({ page }) => {
    await page.goto("/claims");
    await expect(page).toHaveURL(/\/login$/);
  });
});
