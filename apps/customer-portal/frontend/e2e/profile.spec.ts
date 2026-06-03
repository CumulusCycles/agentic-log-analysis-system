import { ALICE, expect, test } from "./fixtures";

test.describe("Profile page", () => {
  test("alice's profile renders username and role", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/profile");
    await expect(
      page.getByRole("heading", { name: /my profile/i }),
    ).toBeVisible();
    // The Username dd renders the lowercase username; the Name dd renders
    // the display_name "Alice". Match the exact lowercase string to avoid
    // colliding with the Name field.
    await expect(page.getByText(ALICE.username, { exact: true })).toBeVisible();
    await expect(page.getByText("customer", { exact: true })).toBeVisible();
  });

  test("anonymous /profile redirects to /login", async ({ page }) => {
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/login$/);
  });
});
