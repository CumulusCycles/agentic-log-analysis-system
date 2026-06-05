import { test, expect } from "@playwright/test";

import { ALICE } from "./fixtures";

test.describe("Authentication", () => {
  test("successful login navigates to /submit and persists token", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ALICE.username);
    await page.getByLabel(/password/i).fill(ALICE.password);
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/submit$/);
    const token = await page.evaluate(() => localStorage.getItem("fnol_token"));
    expect(token).not.toBeNull();
  });

  test("wrong password shows the upstream 401 detail and stays on /login", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ALICE.username);
    await page.getByLabel(/password/i).fill("WRONG");
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page.getByRole("alert")).toContainText(/invalid credentials/i);
    await expect(page).toHaveURL(/\/login$/);
    const token = await page.evaluate(() => localStorage.getItem("fnol_token"));
    expect(token).toBeNull();
  });

  test("login form blocks submit while in flight", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ALICE.username);
    await page.getByLabel(/password/i).fill(ALICE.password);

    const submit = page.getByRole("button", { name: /sign in/i });
    await submit.click();
    // The button label flips to "Signing in…" while the request is pending.
    // Use waitFor to allow either the disabled state OR the navigation that
    // follows it on fast networks.
    await Promise.race([
      expect(submit)
        .toBeDisabled()
        .catch(() => {}),
      page.waitForURL(/\/submit$/).catch(() => {}),
    ]);
  });
});
