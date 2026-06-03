import { expect, test } from "./fixtures";

test.describe("Routing", () => {
  test("anonymous visit to / redirects to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("authenticated / redirects to /policies", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/policies$/);
  });

  test("unknown route redirects to /login when anonymous", async ({ page }) => {
    await page.goto("/this-does-not-exist");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("top nav links navigate between sections when authed", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/policies");
    await page.getByRole("link", { name: /^claims$/i }).click();
    await expect(page).toHaveURL(/\/claims$/);
    await page.getByRole("link", { name: /^profile$/i }).click();
    await expect(page).toHaveURL(/\/profile$/);
    await page.getByRole("link", { name: /^policies$/i }).click();
    await expect(page).toHaveURL(/\/policies$/);
  });
});
