/**
 * Phase 6.75 — verify CP's new log events fire with the expected fields.
 *
 * Pattern: spy on `logger.info` and `logger.warn` after `buildApp` constructs
 * the app graph, then make HTTP requests and assert on the spy's calls.
 *
 * NEVER assert on credential values — tests confirm bearer/password/API key
 * are NOT in any logged event.
 */
import nock from "nock";
import request from "supertest";
import { describe, expect, it, vi } from "vitest";

import { buildApp } from "../src/app.js";
import { makeLogger } from "../src/logger.js";

import { makeToken, TEST_CONFIG } from "./setup.js";

function buildSpyApp() {
  const logger = makeLogger(TEST_CONFIG.LOG_FILE_PATH);
  logger.silent = true;
  const infoSpy = vi.spyOn(logger, "info");
  const warnSpy = vi.spyOn(logger, "warn");
  const { express: app } = buildApp({ cfg: TEST_CONFIG, logger });
  return { app, infoSpy, warnSpy };
}

function eventOf(spy: ReturnType<typeof vi.spyOn>, name: string) {
  return spy.mock.calls.find((call) => call[0] === name);
}

// ---------------------------------------------------------------------------
// login_proxied_success
// ---------------------------------------------------------------------------

describe("CP enrichment — auth", () => {
  it("emits login_proxied_success on successful proxy", async () => {
    const { app, infoSpy } = buildSpyApp();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .post("/auth/login")
      .reply(200, {
        access_token: "tok-x",
        token_type: "bearer",
        expires_in: 60,
      });

    await request(app)
      .post("/auth/login")
      .send({ username: "alice", password: "customer" });

    const call = eventOf(infoSpy, "login_proxied_success");
    expect(call).toBeTruthy();
    expect(call?.[1]).toMatchObject({
      event: "login_proxied_success",
      username: "alice",
    });
    // CRITICAL: password is NEVER in the event payload
    expect(JSON.stringify(call)).not.toContain("customer");
  });
});

// ---------------------------------------------------------------------------
// *_fetched events
// ---------------------------------------------------------------------------

describe("CP enrichment — read paths", () => {
  it("emits policies_fetched with count", async () => {
    const token = makeToken({ user_id: "u-1" });
    const { app, infoSpy } = buildSpyApp();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/policies")
      .query({ customer_id: "u-1" })
      .reply(200, [
        {
          policy_number: "POL-1",
          customer_id: "u-1",
          effective_date: "2025-01-01",
          expiration_date: "2026-01-01",
          coverage_type: "auto",
          premium_cents: 100,
          vehicles: [],
        },
      ]);

    await request(app)
      .get("/policies/me")
      .set("Authorization", `Bearer ${token}`);

    const call = eventOf(infoSpy, "policies_fetched");
    expect(call).toBeTruthy();
    expect(call?.[1]).toMatchObject({
      event: "policies_fetched",
      user_id: "u-1",
      count: 1,
    });
    expect(JSON.stringify(call)).not.toContain(token);
  });

  it("emits claims_fetched with count", async () => {
    const token = makeToken({ user_id: "u-2" });
    const { app, infoSpy } = buildSpyApp();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/claims")
      .query({ customer_id: "u-2" })
      .reply(200, []);

    await request(app)
      .get("/claims/me")
      .set("Authorization", `Bearer ${token}`);

    const call = eventOf(infoSpy, "claims_fetched");
    expect(call?.[1]).toMatchObject({
      event: "claims_fetched",
      user_id: "u-2",
      count: 0,
    });
  });

  it("emits profile_fetched with user_id", async () => {
    const token = makeToken({ user_id: "u-3" });
    const { app, infoSpy } = buildSpyApp();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL).get("/users/u-3").reply(200, {
      id: "u-3",
      username: "alice",
      role: "customer",
      display_name: "Alice",
    });

    await request(app)
      .get("/profile/me")
      .set("Authorization", `Bearer ${token}`);

    const call = eventOf(infoSpy, "profile_fetched");
    expect(call?.[1]).toMatchObject({
      event: "profile_fetched",
      user_id: "u-3",
    });
  });
});

// ---------------------------------------------------------------------------
// sda_upstream_rejected / sda_upstream_unreachable
// ---------------------------------------------------------------------------

describe("CP enrichment — SDA upstream errors", () => {
  it("emits sda_upstream_rejected when SDA returns 4xx", async () => {
    const token = makeToken({ user_id: "u-4" });
    const { app, warnSpy } = buildSpyApp();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/policies")
      .query(true)
      .reply(403, { detail: "forbidden" });

    await request(app)
      .get("/policies/me")
      .set("Authorization", `Bearer ${token}`);

    const call = eventOf(warnSpy, "sda_upstream_rejected");
    expect(call).toBeTruthy();
    expect(call?.[1]).toMatchObject({
      event: "sda_upstream_rejected",
      target: "/policies",
      status: 403,
      detail: "forbidden",
    });
    expect(JSON.stringify(call)).not.toContain(token);
    expect(JSON.stringify(call)).not.toContain(
      TEST_CONFIG.SHARED_DATA_API_KEY_CUSTOMER_PORTAL,
    );
  });

  it("emits sda_upstream_unreachable when SDA is unreachable", async () => {
    const token = makeToken({ user_id: "u-5" });
    const { app, warnSpy } = buildSpyApp();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/policies")
      .query(true)
      .replyWithError({ code: "ECONNREFUSED", message: "boom" });

    await request(app)
      .get("/policies/me")
      .set("Authorization", `Bearer ${token}`);

    const call = eventOf(warnSpy, "sda_upstream_unreachable");
    expect(call).toBeTruthy();
    expect(call?.[1]).toMatchObject({
      event: "sda_upstream_unreachable",
      target: "/policies",
    });
    expect(call?.[1]).toHaveProperty("error_class");
  });
});
