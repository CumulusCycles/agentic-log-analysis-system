/**
 * Mobile-viewport regressions for the FNOL persona — policyholders on phones
 * at accident scenes. These tests are scoped to the `mobile-safari` project
 * in playwright.config.ts (iPhone 14 viewport).
 */
import { ALICE, expect, test } from "./fixtures";

test.skip(
  ({ browserName }) => browserName !== "webkit",
  "Mobile viewport regressions run on the mobile-safari project only.",
);

test.describe("Mobile viewport", () => {
  test("login form fits in the viewport with no horizontal scroll", async ({ page }) => {
    await page.goto("/login");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    expect(overflow).toBe(false);
  });

  test("inputs render with the mobile-readable 16px+ font size", async ({ page }) => {
    await page.goto("/login");
    const fontSize = await page
      .getByRole("textbox", { name: /username/i })
      .evaluate((el) => parseFloat(window.getComputedStyle(el).fontSize));
    // 16px+ prevents iOS Safari from zooming on focus.
    expect(fontSize).toBeGreaterThanOrEqual(16);
  });

  test("submit-claim form button is reachable and tappable above the fold", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: /username/i }).fill(ALICE.username);
    await page.getByLabel(/password/i).fill(ALICE.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/submit$/);

    const submit = page.getByRole("button", { name: /submit claim/i });
    const box = await submit.boundingBox();
    expect(box).not.toBeNull();
    // Apple's HIG recommends 44pt minimum tap target.
    expect(box!.height).toBeGreaterThanOrEqual(40);
  });
});
