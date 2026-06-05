import { AGENT1, expect, test } from "./fixtures";

test.describe("Profile page", () => {
  test("agent profile renders username and role", async ({ loggedInPage: page }) => {
    await page.goto("/profile");
    await expect(page.getByRole("heading", { name: /my profile/i })).toBeVisible();
    // The Username dd renders the lowercase username; the Name dd renders the
    // display_name (e.g. "Agent One"). Match exact lowercase to avoid the
    // substring/case-insensitive collision Playwright getByText applies.
    await expect(page.getByText(AGENT1.username, { exact: true })).toBeVisible();
    await expect(page.getByText("agent", { exact: true })).toBeVisible();
  });

  test("anonymous /profile redirects to /login", async ({ page }) => {
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/login$/);
  });
});
