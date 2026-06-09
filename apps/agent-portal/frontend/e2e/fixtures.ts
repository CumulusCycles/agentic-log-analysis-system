import { test as base, expect, type Page } from "@playwright/test";

// Seeded test data — the SDA seed is deterministic (random.seed(0)) so the
// agent1 account is guaranteed on every cold boot.
//
// Username is read from `TEST_AGENT_USERNAME` (loaded from repo-root
// .env by `playwright.config.ts`) so operators with customised seed
// usernames don't have to edit this file. The default matches the
// `.env.example` value of `AGITATOR_AGENT_USERNAME=agent1`.
export const AGENT1 = {
  username: process.env.TEST_AGENT_USERNAME ?? "agent1",
  password: "agent",
};

interface LoggedInFixture {
  loggedInPage: Page;
  token: string;
  userId: string;
}

async function programmaticLogin(
  page: Page,
  username = AGENT1.username,
  password = AGENT1.password,
): Promise<{ token: string; userId: string }> {
  // Hit /api/auth/login via the page's fetch so the response stays on the
  // same origin. Then stash the token in localStorage before any UI
  // navigation.
  const tokenInfo = await page.request.post("/api/auth/login", {
    data: { username, password },
    headers: { "Content-Type": "application/json" },
  });
  expect(tokenInfo.ok()).toBe(true);
  const { access_token } = (await tokenInfo.json()) as {
    access_token: string;
  };

  const payloadB64 = access_token.split(".")[1];
  const payload = JSON.parse(
    Buffer.from(payloadB64.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString(),
  ) as { user_id: string };

  await page.goto("/");
  await page.evaluate(
    ({ token }) => {
      localStorage.setItem("agent_portal_token", token);
    },
    { token: access_token },
  );

  return { token: access_token, userId: payload.user_id };
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
  userId: async ({ page }, use) => {
    const { userId } = await programmaticLogin(page);
    await use(userId);
  },
});

export { expect, programmaticLogin };
