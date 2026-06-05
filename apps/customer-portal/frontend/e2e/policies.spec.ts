import { ALICE, expect, test } from "./fixtures";

test.describe("Policies page", () => {
  test("alice's policies render with POL-1004 and at least one vehicle", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/policies");
    await expect(page.getByRole("heading", { name: /my policies/i })).toBeVisible();

    await expect(page.getByText(ALICE.policyNumber)).toBeVisible();

    // At least one vehicle row should be present — every seeded policy has
    // 1–2 vehicles with a 17-character VIN.
    const vinPattern = /[A-HJ-NPR-Z0-9]{17}/;
    await expect(page.getByText(vinPattern).first()).toBeVisible();
  });

  test("anonymous /policies redirects to /login", async ({ page }) => {
    await page.goto("/policies");
    await expect(page).toHaveURL(/\/login$/);
  });
});
