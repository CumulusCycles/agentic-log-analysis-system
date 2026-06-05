import { ALICE, expect, test } from "./fixtures";

test.describe("Submit claim", () => {
  test("submits a valid claim and navigates to the detail page", async ({ loggedInPage: page }) => {
    await page.goto("/submit");

    await page.getByLabel(/policy number/i).fill(ALICE.policyNumber);
    await page.getByLabel(/vin/i).fill(ALICE.vin);

    // datetime-local takes "YYYY-MM-DDTHH:MM" format.
    await page.getByLabel(/incident date/i).fill("2026-06-01T10:00");
    await page.getByLabel(/what happened/i).fill("Rear-ended at intersection (e2e test)");

    await page.getByRole("button", { name: /submit claim/i }).click();

    // Redirected to /claims/<uuid>
    await expect(page).toHaveURL(/\/claims\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { name: /^Claim/ })).toBeVisible();
  });

  test("required HTML5 validation prevents submit with empty fields", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/submit");
    await page.getByRole("button", { name: /submit claim/i }).click();
    // We never leave /submit because required fields are empty.
    await expect(page).toHaveURL(/\/submit$/);
  });

  test("SDA-side error surfaces in an alert on the form", async ({ loggedInPage: page }) => {
    await page.goto("/submit");
    // Bogus VIN — SDA will validate against the policy and return 400.
    await page.getByLabel(/policy number/i).fill(ALICE.policyNumber);
    await page.getByLabel(/vin/i).fill("NOTAREALVIN0000000");
    await page.getByLabel(/incident date/i).fill("2026-06-01T10:00");
    await page.getByLabel(/what happened/i).fill("bogus VIN test");
    await page.getByRole("button", { name: /submit claim/i }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/submit$/);
  });

  test("sign-out clears the token and returns to /login", async ({ loggedInPage: page }) => {
    await page.goto("/submit");
    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login$/);
    const token = await page.evaluate(() => localStorage.getItem("fnol_token"));
    expect(token).toBeNull();
  });
});
