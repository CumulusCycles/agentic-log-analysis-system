/**
 * Chaos middleware — ENABLE_CHAOS env gate + X-Chaos directive grammar.
 *
 * Covers the CP chaos middleware behavior contract (per ADR-013):
 *   - ENABLE_CHAOS=false  -> header ignored, normal request flow
 *   - ENABLE_CHAOS=true + slow:<ms>    -> setTimeout(ms), then continue
 *   - ENABLE_CHAOS=true + error:<code> -> immediate response with that code
 *   - ENABLE_CHAOS=true + malformed    -> 400 + chaos_directive_invalid WARN
 *   - chaos_honored WARN fires with the expected fields
 */
import request from "supertest";
import { describe, expect, it, vi } from "vitest";

import { buildApp } from "../src/app.js";
import type { Config } from "../src/config.js";
import { makeLogger } from "../src/logger.js";

import { TEST_CONFIG } from "./setup.js";

function buildSpyApp(overrides: Partial<Config> = {}) {
  const cfg: Config = { ...TEST_CONFIG, ...overrides };
  const logger = makeLogger(cfg.LOG_FILE_PATH);
  logger.silent = true;
  const warnSpy = vi.spyOn(logger, "warn");
  const errorSpy = vi.spyOn(logger, "error");
  const { express: app } = buildApp({ cfg, logger });
  return { app, warnSpy, errorSpy };
}

function eventOf(spy: ReturnType<typeof vi.spyOn>, name: string) {
  return spy.mock.calls.find((call) => call[0] === name);
}

describe("CP chaos — gate", () => {
  it("ignores X-Chaos when ENABLE_CHAOS=false", async () => {
    const { app, warnSpy } = buildSpyApp({ ENABLE_CHAOS: false });
    const resp = await request(app).get("/health").set("X-Chaos", "error:503");
    expect(resp.status).toBe(200);
    expect(eventOf(warnSpy, "chaos_honored")).toBeFalsy();
  });

  it("passes through with no X-Chaos header even when chaos enabled", async () => {
    const { app, warnSpy } = buildSpyApp({ ENABLE_CHAOS: true });
    const resp = await request(app).get("/health");
    expect(resp.status).toBe(200);
    expect(eventOf(warnSpy, "chaos_honored")).toBeFalsy();
  });
});

describe("CP chaos — directives", () => {
  it("slow:<ms> delays and continues to the handler", async () => {
    const { app, warnSpy } = buildSpyApp({ ENABLE_CHAOS: true });
    const start = Date.now();
    const resp = await request(app).get("/health").set("X-Chaos", "slow:120");
    const elapsed = Date.now() - start;
    expect(resp.status).toBe(200);
    // setTimeout can fire a tick early on some Node runtimes; allow a small fudge.
    expect(elapsed).toBeGreaterThanOrEqual(110);
    const call = eventOf(warnSpy, "chaos_honored");
    expect(call).toBeTruthy();
    expect(call?.[1]).toMatchObject({
      event: "chaos_honored",
      directive: "slow:120",
      delay_ms: 120,
      method: "GET",
      path: "/health",
    });
  });

  it("error:<5xx> returns that status AND logs chaos_honored at ERROR level", async () => {
    // PR 4c: 5xx chaos returns are escalated to ERROR so the dashboard's
    // proactive scan sees ERROR-tier signal in Chroma.
    const { app, warnSpy, errorSpy } = buildSpyApp({ ENABLE_CHAOS: true });
    const resp = await request(app).get("/health").set("X-Chaos", "error:503");
    expect(resp.status).toBe(503);
    expect(resp.body).toEqual({ detail: "chaos" });
    const errCall = eventOf(errorSpy, "chaos_honored");
    expect(errCall?.[1]).toMatchObject({
      event: "chaos_honored",
      directive: "error:503",
      status: 503,
    });
    // ...and chaos_honored MUST NOT also have fired at WARN.
    expect(eventOf(warnSpy, "chaos_honored")).toBeFalsy();
  });

  it("error:<4xx> stays at WARN level", async () => {
    // Operator-driven 4xx is not a server failure — keep it WARN so the
    // proactive scan's ERROR-tier signal stays sharp.
    const { app, warnSpy, errorSpy } = buildSpyApp({ ENABLE_CHAOS: true });
    const resp = await request(app).get("/health").set("X-Chaos", "error:418");
    expect(resp.status).toBe(418);
    const warnCall = eventOf(warnSpy, "chaos_honored");
    expect(warnCall?.[1]).toMatchObject({
      event: "chaos_honored",
      directive: "error:418",
      status: 418,
    });
    expect(eventOf(errorSpy, "chaos_honored")).toBeFalsy();
  });

  it.each([
    "garbage",
    "slow:abc",
    "slow:-1",
    "slow:60001",
    "error:399",
    "error:600",
    "unknown:200",
  ])("malformed directive %s -> 400 + chaos_directive_invalid", async (directive) => {
    const { app, warnSpy } = buildSpyApp({ ENABLE_CHAOS: true });
    const resp = await request(app).get("/health").set("X-Chaos", directive);
    expect(resp.status).toBe(400);
    expect(resp.body.detail).toContain("invalid X-Chaos directive");
    const call = eventOf(warnSpy, "chaos_directive_invalid");
    expect(call?.[1]).toMatchObject({
      event: "chaos_directive_invalid",
      directive_raw: directive,
      reason: "malformed",
    });
  });
});
