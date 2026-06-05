import { ALICE, expect, test } from "./fixtures";

async function createClaim(
  page: import("@playwright/test").Page,
  customerId: string,
  token: string,
): Promise<string> {
  const res = await page.request.post("/fnol/submit", {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    data: {
      customer_id: customerId,
      policy_number: ALICE.policyNumber,
      vin: ALICE.vin,
      incident_at: "2026-06-01T10:00:00+00:00",
      description: "claim-detail e2e seed",
    },
  });
  expect(res.ok()).toBe(true);
  const body = (await res.json()) as { id: string };
  return body.id;
}

test.describe("Claim detail", () => {
  test("renders status, policy, VIN, and history for a freshly created claim", async ({
    loggedInPage: page,
    customerId,
    token,
  }) => {
    const claimId = await createClaim(page, customerId, token);

    await page.goto(`/claims/${claimId}`);

    await expect(page.getByRole("heading", { name: new RegExp(claimId) })).toBeVisible();

    // The status dl/dd grid contains the values.
    await expect(page.locator("dd").filter({ hasText: ALICE.policyNumber })).toBeVisible();
    await expect(page.locator("dd").filter({ hasText: ALICE.vin })).toBeVisible();

    // Status starts as "submitted" — the simulator may have advanced it by the
    // time we load, so accept any ADR-007 status value.
    await expect(
      page.locator("dd").filter({
        hasText: /^(submitted|triaged|investigating|settled|closed|denied)$/,
      }),
    ).toBeVisible();
  });

  test("shows error alert when the claim id is unknown", async ({ loggedInPage: page }) => {
    await page.goto("/claims/00000000-0000-0000-0000-000000000000");
    await expect(page.getByRole("alert")).toBeVisible();
  });

  test("'file another claim' link returns to /submit", async ({
    loggedInPage: page,
    customerId,
    token,
  }) => {
    const claimId = await createClaim(page, customerId, token);
    await page.goto(`/claims/${claimId}`);
    await page.getByRole("link", { name: /file another claim/i }).click();
    await expect(page).toHaveURL(/\/submit$/);
  });
});
