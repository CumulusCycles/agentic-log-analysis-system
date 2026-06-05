import nock from "nock";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { buildTestApp, TEST_CONFIG } from "./setup.js";

describe("POST /auth/login", () => {
  it("proxies the SDA token response on success", async () => {
    const scope = nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .post("/auth/login", { username: "alice", password: "customer" })
      .reply(200, {
        access_token: "tok-abc",
        token_type: "bearer",
        expires_in: 3600,
      });

    const { express: app } = buildTestApp();
    const res = await request(app)
      .post("/auth/login")
      .send({ username: "alice", password: "customer" });

    expect(res.status).toBe(200);
    expect(res.body.access_token).toBe("tok-abc");
    scope.done();
  });

  it("forwards CP's X-API-Key on the outbound SDA call", async () => {
    // ADR-006 §1: X-API-Key required on every SDA call, including /auth/login.
    let receivedKey: string | undefined;
    const scope = nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .post("/auth/login")
      .reply(function () {
        receivedKey = this.req.headers["x-api-key"] as string | undefined;
        return [200, { access_token: "x", token_type: "bearer", expires_in: 60 }];
      });

    const { express: app } = buildTestApp();
    await request(app).post("/auth/login").send({ username: "alice", password: "customer" });

    expect(receivedKey).toBe(TEST_CONFIG.SHARED_DATA_API_KEY_CUSTOMER_PORTAL);
    scope.done();
  });

  it("passes a 401 from SDA back to the client", async () => {
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .post("/auth/login")
      .reply(401, { detail: "invalid credentials" });

    const { express: app } = buildTestApp();
    const res = await request(app)
      .post("/auth/login")
      .send({ username: "alice", password: "WRONG" });

    expect(res.status).toBe(401);
    expect(res.body).toEqual({ detail: "invalid credentials" });
  });

  it("returns 502 when SDA is unreachable", async () => {
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .post("/auth/login")
      .replyWithError({ code: "ECONNREFUSED", message: "boom" });

    const { express: app } = buildTestApp();
    const res = await request(app).post("/auth/login").send({ username: "alice", password: "x" });

    expect(res.status).toBe(502);
    expect(res.body.detail).toMatch(/unreachable/i);
  });

  it("returns 422 when the body is malformed", async () => {
    const { express: app } = buildTestApp();
    const res = await request(app).post("/auth/login").send({ username: "alice" });
    expect(res.status).toBe(422);
  });
});
