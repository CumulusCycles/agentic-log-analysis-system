import { test, expect } from "./fixtures";

// Log Generator tab — operator-button-only scenario runner.
//
// Stubs the Agitator API so the spec is deterministic regardless of what's
// in the live RunRegistry when the suite runs. Two projects (desktop /
// mobile) — matches the pattern of the other dashboard E2E specs.

const SCENARIOS = [
  {
    name: "auth-spike",
    display_name: "Auth spike",
    description: "50 failed FNOL logins over 30 seconds.",
    target_app: "fnol",
    requires_chaos: false,
    params: [
      { name: "count", minimum: 1, maximum: 500, default: 50 },
      { name: "duration_s", minimum: 1, maximum: 300, default: 30 },
    ],
  },
  {
    name: "cp-read-burst",
    display_name: "CP read burst",
    description: "120 GET /policies/me from the customer portal over 60s.",
    target_app: "customer-portal",
    requires_chaos: false,
    params: [
      { name: "count", minimum: 1, maximum: 500, default: 120 },
      { name: "duration_s", minimum: 1, maximum: 300, default: 60 },
    ],
  },
];

const STARTED_RUN = {
  run_id: "auth-fresh",
  scenario: "auth-spike",
  params: { count: 50, duration_s: 30 },
  state: "running" as const,
  started_at: "2026-06-07T12:00:00Z",
  ended_at: null,
  sent: 0,
  succeeded: 0,
  failed: 0,
  last_status_code: null,
  last_error: null,
};

test.describe("Log Generator tab", () => {
  test("renders each scenario as its own card with per-card run history", async ({
    loggedInPage: page,
  }) => {
    await page.route(/\/api\/agitator\/scenarios/, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(SCENARIOS),
      }),
    );
    await page.route(/\/api\/agitator\/env/, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable_chaos: false }),
      }),
    );
    await page.route(/\/api\/agitator\/runs$/, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          runs: [
            STARTED_RUN,
            // Add a run that belongs to a DIFFERENT scenario so per-card
            // scoping can be observed in the assertions below.
            {
              ...STARTED_RUN,
              run_id: "cp-r1",
              scenario: "cp-read-burst",
              state: "succeeded",
              sent: 120,
              succeeded: 120,
            },
          ],
        }),
      }),
    );

    await page.goto("/log-generator");

    // Both cards render with their per-card recent-runs strip.
    await expect(page.getByTestId("scenario-card-auth-spike")).toBeVisible();
    await expect(page.getByTestId("scenario-card-cp-read-burst")).toBeVisible();

    // The auth card holds its own run; the cp card holds its own; neither
    // leaks into the other.
    const authCard = page.getByTestId("scenario-runs-auth-spike");
    await expect(authCard.getByTestId("run-row-auth-fresh")).toBeVisible();
    await expect(authCard.getByTestId("run-row-cp-r1")).toHaveCount(0);

    const cpCard = page.getByTestId("scenario-runs-cp-read-burst");
    await expect(cpCard.getByTestId("run-row-cp-r1")).toBeVisible();
    await expect(cpCard.getByTestId("run-row-auth-fresh")).toHaveCount(0);

    // The pre-PR-3 standalone Recent runs panel is gone.
    await expect(page.getByTestId("recent-runs")).toHaveCount(0);
  });

  test("clicking Run posts to /api/agitator/runs and the row appears inside the matching card", async ({
    loggedInPage: page,
  }) => {
    let started = false;
    await page.route(/\/api\/agitator\/scenarios/, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(SCENARIOS),
      }),
    );
    await page.route(/\/api\/agitator\/env/, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable_chaos: false }),
      }),
    );
    await page.route(/\/api\/agitator\/runs$/, async (route, request) => {
      if (request.method() === "POST") {
        started = true;
        await route.fulfill({
          status: 201,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(STARTED_RUN),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ runs: started ? [STARTED_RUN] : [] }),
      });
    });

    await page.goto("/log-generator");
    await expect(page.getByTestId("scenario-card-auth-spike")).toBeVisible();

    await page.getByTestId("run-button-auth-spike").click();

    // New run row appears inside the auth-spike card.
    const authCard = page.getByTestId("scenario-runs-auth-spike");
    await expect(authCard.getByTestId("run-row-auth-fresh")).toBeVisible();
    // A running row carries a Cancel button per-card.
    await expect(authCard.getByTestId("cancel-button-auth-fresh")).toBeVisible();
  });
});
