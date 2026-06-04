import { test, expect } from "@playwright/test";

import { ADMIN } from "./fixtures";

async function getToken(request: import("@playwright/test").APIRequestContext) {
  const res = await request.post("/api/auth/login", {
    data: { username: ADMIN.username, password: ADMIN.password },
    headers: { "Content-Type": "application/json" },
  });
  expect(res.ok()).toBe(true);
  const { access_token } = (await res.json()) as { access_token: string };
  return access_token;
}

test.describe("Read-only log API (7b)", () => {
  test("authenticated GET /api/status returns 4 apps with the expected shape", async ({
    request,
  }) => {
    const token = await getToken(request);
    const res = await request.get("/api/status", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const body = (await res.json()) as {
      as_of: string;
      apps: Array<{
        name: string;
        status: string;
        file_present: boolean;
        last_seen_at: string | null;
        counts_1h: { info: number; warn: number; error: number };
      }>;
    };
    expect(body.apps.map((a) => a.name)).toEqual([
      "shared-data-api",
      "fnol",
      "customer-portal",
      "agent-portal",
    ]);
    for (const app of body.apps) {
      expect(["ok", "degraded", "error"]).toContain(app.status);
      expect(app.file_present).toBe(true);
      expect(app.counts_1h.info).toBeGreaterThanOrEqual(0);
    }
  });

  test("authenticated GET /api/logs?limit=5 returns at most 5 entries newest-first", async ({
    request,
  }) => {
    const token = await getToken(request);
    const res = await request.get("/api/logs?limit=5", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const body = (await res.json()) as {
      entries: Array<{
        id: string;
        timestamp: string;
        level: string;
        app: string;
      }>;
      next_before: string | null;
    };
    expect(body.entries.length).toBeLessThanOrEqual(5);
    const timestamps = body.entries.map((e) => e.timestamp);
    const sorted = [...timestamps].sort().reverse();
    expect(timestamps).toEqual(sorted);
  });

  test("unauthenticated /api/logs and /api/status return 401", async ({
    request,
  }) => {
    const statusRes = await request.get("/api/status");
    expect(statusRes.status()).toBe(401);
    const logsRes = await request.get("/api/logs");
    expect(logsRes.status()).toBe(401);
  });

  test("filter app=shared-data-api&level=ERROR,WARN returns only matching entries", async ({
    request,
  }) => {
    const token = await getToken(request);
    const res = await request.get(
      "/api/logs?app=shared-data-api&level=ERROR,WARN&limit=20",
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(res.status()).toBe(200);
    const body = (await res.json()) as {
      entries: Array<{ app: string; level: string }>;
    };
    for (const entry of body.entries) {
      expect(entry.app).toBe("shared-data-api");
      expect(["ERROR", "WARN"]).toContain(entry.level);
    }
  });
});
