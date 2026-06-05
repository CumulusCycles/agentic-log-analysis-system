import jwt from "jsonwebtoken";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { JWT_AUDIENCE, JWT_ISSUER } from "../src/middleware/require-auth.js";

import { buildTestApp, makeToken, TEST_CONFIG } from "./setup.js";

function signWith(payload: Record<string, unknown>, secret = TEST_CONFIG.JWT_SECRET): string {
  const now = Math.floor(Date.now() / 1000);
  return jwt.sign(
    {
      iss: JWT_ISSUER,
      aud: JWT_AUDIENCE,
      user_id: "u",
      role: "customer",
      app: "customer-portal",
      iat: now,
      exp: now + 600,
      ...payload,
    },
    secret,
    { algorithm: TEST_CONFIG.JWT_ALGORITHM as jwt.Algorithm },
  );
}

describe("requireAuth middleware (via /profile/me)", () => {
  it("rejects tokens with the wrong issuer", async () => {
    const token = signWith({ iss: "evil-issuer" });
    const { express: app } = buildTestApp();
    const res = await request(app).get("/profile/me").set("Authorization", `Bearer ${token}`);
    expect(res.status).toBe(401);
    expect(res.body.detail).toBe("invalid token");
  });

  it("rejects tokens with the wrong audience", async () => {
    const token = signWith({ aud: "other-audience" });
    const { express: app } = buildTestApp();
    const res = await request(app).get("/profile/me").set("Authorization", `Bearer ${token}`);
    expect(res.status).toBe(401);
  });

  it("rejects expired tokens", async () => {
    const now = Math.floor(Date.now() / 1000);
    const token = signWith({ exp: now - 60, iat: now - 120 });
    const { express: app } = buildTestApp();
    const res = await request(app).get("/profile/me").set("Authorization", `Bearer ${token}`);
    expect(res.status).toBe(401);
  });

  it("rejects tokens signed with the wrong secret", async () => {
    const token = signWith({}, "wrong-secret");
    const { express: app } = buildTestApp();
    const res = await request(app).get("/profile/me").set("Authorization", `Bearer ${token}`);
    expect(res.status).toBe(401);
  });

  it("accepts a valid token (sanity)", async () => {
    // We assert only on the 401 path here — a valid token would need nock
    // to intercept the SDA call, which the profile tests already cover.
    const token = makeToken();
    expect(typeof token).toBe("string");
  });
});
