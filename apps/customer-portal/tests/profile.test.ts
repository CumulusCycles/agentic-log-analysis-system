import nock from "nock";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { buildTestApp, makeToken, TEST_CONFIG } from "./setup.js";

describe("GET /profile/me", () => {
  it("returns the SDA user profile", async () => {
    const token = makeToken({ user_id: "u-1" });
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL).get("/users/u-1").reply(200, {
      id: "u-1",
      username: "alice",
      role: "customer",
      display_name: "Alice Anderson",
    });

    const { express: app } = buildTestApp();
    const res = await request(app)
      .get("/profile/me")
      .set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.username).toBe("alice");
    expect(res.body.display_name).toBe("Alice Anderson");
  });

  it("returns 401 when the Authorization header is missing", async () => {
    const { express: app } = buildTestApp();
    const res = await request(app).get("/profile/me");
    expect(res.status).toBe(401);
    expect(res.body.detail).toMatch(/missing bearer token/i);
  });

  it("returns 401 for an invalid token", async () => {
    const { express: app } = buildTestApp();
    const res = await request(app)
      .get("/profile/me")
      .set("Authorization", "Bearer not-a-jwt");
    expect(res.status).toBe(401);
    expect(res.body.detail).toBe("invalid token");
  });

  it("forwards a 404 from SDA verbatim", async () => {
    const token = makeToken({ user_id: "u-missing" });
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/users/u-missing")
      .reply(404, { detail: "user not found" });

    const { express: app } = buildTestApp();
    const res = await request(app)
      .get("/profile/me")
      .set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(404);
    expect(res.body).toEqual({ detail: "user not found" });
  });
});
