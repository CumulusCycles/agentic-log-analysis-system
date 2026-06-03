import { expect, test } from "./fixtures";

test.describe("Routing", () => {
  test("anonymous visit to / redirects to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("anonymous visit to /submit redirects to /login", async ({ page }) => {
    await page.goto("/submit");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("anonymous visit to /claims/<id> redirects to /login", async ({
    page,
  }) => {
    await page.goto("/claims/anything");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("unknown route redirects to /login when anonymous", async ({ page }) => {
    await page.goto("/this-does-not-exist");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("authenticated / redirects to /submit", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/submit$/);
  });
});
