import { test, expect } from "@playwright/test";

import { ALICE } from "./fixtures";

test.describe("Authentication", () => {
  test("successful login navigates to /policies and persists token", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ALICE.username);
    await page.getByLabel(/password/i).fill(ALICE.password);
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/policies$/);
    const token = await page.evaluate(() =>
      localStorage.getItem("customer_portal_token"),
    );
    expect(token).not.toBeNull();
  });

  test("wrong password shows the upstream 401 detail and stays on /login", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ALICE.username);
    await page.getByLabel(/password/i).fill("WRONG");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByRole("alert")).toContainText(/invalid credentials/i);
    await expect(page).toHaveURL(/\/login$/);
    const token = await page.evaluate(() =>
      localStorage.getItem("customer_portal_token"),
    );
    expect(token).toBeNull();
  });

  test("wrong username shows the upstream 401 detail and stays on /login", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill("nobody");
    await page.getByLabel(/password/i).fill("customer");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("sign out clears the token and returns to /login", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ALICE.username);
    await page.getByLabel(/password/i).fill(ALICE.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/policies$/);

    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login$/);
    const token = await page.evaluate(() =>
      localStorage.getItem("customer_portal_token"),
    );
    expect(token).toBeNull();
  });
});
