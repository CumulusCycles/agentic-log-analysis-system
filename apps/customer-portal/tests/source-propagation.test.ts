import express from "express";
import request from "supertest";
import { describe, expect, it, vi } from "vitest";

import type { Logger } from "../src/logger.js";
import { requestLogger } from "../src/middleware/request-logger.js";
import { getCurrentSource, normalizeSource, runWithSource } from "../src/source-context.js";

/** Lightweight Logger stub — records info() calls so tests can assert on
 *  the captured `source` field without spinning up a real winston pipeline. */
interface CapturedCall {
  event: string;
  source?: string;
  [k: string]: unknown;
}

function silentLogger(captured: CapturedCall[] = []): Logger {
  return {
    info: (_msg: string, meta: Record<string, unknown> = {}) => {
      captured.push({ event: String(meta.event ?? _msg), ...meta });
    },
    warn: () => undefined,
    error: () => undefined,
    debug: () => undefined,
    log: () => undefined,
  } as unknown as Logger;
}

describe("normalizeSource", () => {
  it.each([
    ["synthetic", "synthetic"],
    ["Synthetic", "synthetic"],
    ["  test  ", "test"],
    ["PROD", "prod"],
    [undefined, "prod"],
    ["", "prod"],
    ["   ", "prod"],
    // Defensive: anything that doesn't look like a clean token falls to prod
    // so a malicious caller can't inject log content via the header.
    ["foo bar", "prod"],
    ["weird!chars", "prod"],
  ])("normalizes %j -> %j", (raw, expected) => {
    expect(normalizeSource(raw)).toBe(expected);
  });
});

describe("runWithSource / getCurrentSource", () => {
  it("getCurrentSource returns prod when no ALS context is active", () => {
    expect(getCurrentSource()).toBe("prod");
  });

  it("runWithSource exposes the value inside the callback", () => {
    let seen: string | undefined;
    runWithSource("synthetic", () => {
      seen = getCurrentSource();
    });
    expect(seen).toBe("synthetic");
    // And the context unwinds — outside the callback, no source is bound.
    expect(getCurrentSource()).toBe("prod");
  });

  it("propagates through async callbacks (the whole point of ALS)", async () => {
    let asyncSeen: string | undefined;
    await runWithSource("test", async () => {
      await new Promise((resolve) => setImmediate(resolve));
      asyncSeen = getCurrentSource();
    });
    expect(asyncSeen).toBe("test");
  });
});

describe("requestLogger middleware", () => {
  it("emits source from X-Source header in the request log line", async () => {
    const captured: CapturedCall[] = [];
    const logger = silentLogger(captured);
    const app = express();
    app.use(requestLogger(logger));
    app.get("/probe", (_, res) => {
      // While inside the handler the ALS context is active.
      res.locals.snapshot = getCurrentSource();
      res.json({ source: res.locals.snapshot });
    });

    const r = await request(app).get("/probe").set("X-Source", "synthetic");
    expect(r.status).toBe(200);
    expect(r.body.source).toBe("synthetic");
    const requestLine = captured.find((c) => c.event === "request");
    expect(requestLine?.source).toBe("synthetic");
  });

  it("defaults to prod when no X-Source header is sent", async () => {
    const captured: CapturedCall[] = [];
    const logger = silentLogger(captured);
    const app = express();
    app.use(requestLogger(logger));
    app.get("/probe", (_, res) => res.json({ source: getCurrentSource() }));

    const r = await request(app).get("/probe");
    expect(r.body.source).toBe("prod");
    const requestLine = captured.find((c) => c.event === "request");
    expect(requestLine?.source).toBe("prod");
  });

  it("normalises header value before binding (case + whitespace)", async () => {
    const app = express();
    app.use(requestLogger(silentLogger()));
    app.get("/probe", (_, res) => res.json({ source: getCurrentSource() }));

    const r = await request(app).get("/probe").set("X-Source", "  Test  ");
    expect(r.body.source).toBe("test");
  });

  it("does not leak source from one request into the next", async () => {
    const app = express();
    app.use(requestLogger(silentLogger()));
    app.get("/probe", (_, res) => res.json({ source: getCurrentSource() }));

    const first = await request(app).get("/probe").set("X-Source", "synthetic");
    expect(first.body.source).toBe("synthetic");
    const second = await request(app).get("/probe");
    expect(second.body.source).toBe("prod");
  });
});

describe("SdaClient interceptor (X-Source forwarding)", () => {
  it("forwards the active source onto every outbound request", async () => {
    // Drive the registered interceptor directly. We don't spin up axios —
    // the test exercises the closure-captured logic that reads the ALS.
    const axios = await import("axios");
    const interceptors: Array<(cfg: { headers: Headers }) => unknown> = [];
    const createSpy = vi.spyOn(axios.default, "create").mockReturnValue({
      interceptors: {
        request: { use: (fn: (cfg: { headers: Headers }) => unknown) => interceptors.push(fn) },
      },
    } as never);
    const { SharedDataAPIClient } = await import("../src/clients/sda-client.js");
    new SharedDataAPIClient(
      {
        SHARED_DATA_API_BASE_URL: "http://sda",
        SHARED_DATA_API_KEY_CUSTOMER_PORTAL: "k",
      } as never,
      silentLogger() as never,
    );
    expect(interceptors).toHaveLength(1);

    const headerCaptures: Record<string, string> = {};
    const fakeConfig = {
      headers: {
        set(key: string, value: string) {
          headerCaptures[key] = value;
        },
      } as unknown as Headers,
    };

    runWithSource("test", () => interceptors[0](fakeConfig));
    expect(headerCaptures["X-Source"]).toBe("test");

    runWithSource("synthetic", () => interceptors[0](fakeConfig));
    expect(headerCaptures["X-Source"]).toBe("synthetic");

    createSpy.mockRestore();
  });
});
