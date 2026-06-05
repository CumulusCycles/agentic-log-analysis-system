import { test as base, expect, type Page } from "@playwright/test";

// Seeded test data — the SDA seed is deterministic (random.seed(0)) so alice
// has the same policy + vehicles on every cold boot. If the seed shape ever
// changes, these tests will fail loudly and need updating.
export const ALICE = {
  username: "alice",
  password: "customer",
  policyNumber: "POL-1004",
  vin: "BH0WSDSFF8EJJ7LT4",
};

interface LoggedInFixture {
  loggedInPage: Page;
  token: string;
  customerId: string;
}

async function programmaticLogin(
  page: Page,
  username = ALICE.username,
  password = ALICE.password,
): Promise<{ token: string; customerId: string }> {
  // Hit /auth/login via the page's fetch so the response stays on the same
  // origin. Then stash the token in localStorage before any UI navigation.
  const tokenInfo = await page.request.post("/auth/login", {
    data: { username, password },
    headers: { "Content-Type": "application/json" },
  });
  expect(tokenInfo.ok()).toBe(true);
  const { access_token } = (await tokenInfo.json()) as { access_token: string };

  const payloadB64 = access_token.split(".")[1];
  const payload = JSON.parse(
    Buffer.from(payloadB64.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString(),
  ) as { user_id: string };

  await page.goto("/");
  await page.evaluate(
    ({ token }) => {
      localStorage.setItem("fnol_token", token);
    },
    { token: access_token },
  );

  return { token: access_token, customerId: payload.user_id };
}

export const test = base.extend<LoggedInFixture>({
  loggedInPage: async ({ page }, use) => {
    await programmaticLogin(page);
    await use(page);
  },
  token: async ({ page }, use) => {
    const { token } = await programmaticLogin(page);
    await use(token);
  },
  customerId: async ({ page }, use) => {
    const { customerId } = await programmaticLogin(page);
    await use(customerId);
  },
});

export { expect, programmaticLogin };
