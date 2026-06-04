import { test, expect } from "@playwright/test";

import { ADMIN } from "./fixtures";

test.describe("Authentication", () => {
  test("successful login navigates to / and persists token", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ADMIN.username);
    await page.getByLabel(/password/i).fill(ADMIN.password);
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { name: /^overview$/i }),
    ).toBeVisible();
    const token = await page.evaluate(() =>
      localStorage.getItem("dashboard_token"),
    );
    expect(token).not.toBeNull();
  });

  test("wrong password shows the upstream 401 detail and stays on /login", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ADMIN.username);
    await page.getByLabel(/password/i).fill("WRONG");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByRole("alert")).toContainText(/invalid credentials/i);
    await expect(page).toHaveURL(/\/login$/);
    const token = await page.evaluate(() =>
      localStorage.getItem("dashboard_token"),
    );
    expect(token).toBeNull();
  });

  test("unauthenticated visit to / redirects to /login", async ({ page }) => {
    // Visit any same-origin page first so the page has a context in which
    // localStorage can be cleared, then navigate to / unauthenticated.
    await page.goto("/login");
    await page.evaluate(() => localStorage.removeItem("dashboard_token"));
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("logout clears token and returns to /login", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ADMIN.username);
    await page.getByLabel(/password/i).fill(ADMIN.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/$/);

    await page.getByRole("button", { name: /log out/i }).click();
    await expect(page).toHaveURL(/\/login$/);
    const token = await page.evaluate(() =>
      localStorage.getItem("dashboard_token"),
    );
    expect(token).toBeNull();
  });

  test("refresh after login preserves session", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ADMIN.username);
    await page.getByLabel(/password/i).fill(ADMIN.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/$/);

    await page.reload();
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { name: /^overview$/i }),
    ).toBeVisible();
  });
});
