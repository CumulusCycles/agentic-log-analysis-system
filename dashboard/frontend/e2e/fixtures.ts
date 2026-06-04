import { test as base, expect, type Page } from "@playwright/test";

// Admin credentials are env-supplied. The Playwright suite assumes the live
// dashboard container is up with the default `.env.example` values.
export const ADMIN = {
  username: process.env.DASHBOARD_ADMIN_USERNAME ?? "Admin",
  password: process.env.DASHBOARD_ADMIN_PASSWORD ?? "Admin",
};

interface LoggedInFixture {
  loggedInPage: Page;
  token: string;
}

async function programmaticLogin(page: Page): Promise<{ token: string }> {
  const res = await page.request.post("/api/auth/login", {
    data: { username: ADMIN.username, password: ADMIN.password },
    headers: { "Content-Type": "application/json" },
  });
  expect(res.ok()).toBe(true);
  const { access_token } = (await res.json()) as { access_token: string };

  await page.goto("/");
  await page.evaluate(
    ({ token }) => {
      localStorage.setItem("dashboard_token", token);
    },
    { token: access_token },
  );

  return { token: access_token };
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
});

export { expect, programmaticLogin };
