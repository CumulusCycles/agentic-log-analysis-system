import express from "express";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { AppError } from "../src/errors.js";
import { makeLogger } from "../src/logger.js";
import { errorHandler } from "../src/middleware/error-handler.js";

function buildIsolatedApp() {
  const app = express();
  app.use(express.json({ limit: "1mb" }));

  app.get("/throw-app-error", (_req, _res, next) => {
    next(new AppError(401, "unauthorized"));
  });
  app.get("/throw-plain", (_req, _res, next) => {
    next(new Error("kaboom — must not leak into response body"));
  });
  app.post("/echo", (req, res) => {
    res.json(req.body);
  });

  const logger = makeLogger("/tmp/cp-error-handler-test.log");
  logger.silent = true;
  app.use(errorHandler(logger));
  return app;
}

describe("errorHandler", () => {
  it("emits AppError status + detail verbatim", async () => {
    const res = await request(buildIsolatedApp()).get("/throw-app-error");
    expect(res.status).toBe(401);
    expect(res.body).toEqual({ detail: "unauthorized" });
  });

  it("returns 500 with generic detail for unexpected errors (no message leak)", async () => {
    const res = await request(buildIsolatedApp()).get("/throw-plain");
    expect(res.status).toBe(500);
    expect(res.body).toEqual({ detail: "internal server error" });
    expect(res.text).not.toContain("kaboom");
  });

  it("returns 400 for malformed JSON body", async () => {
    const res = await request(buildIsolatedApp())
      .post("/echo")
      .set("Content-Type", "application/json")
      .send("{ not valid json");
    expect(res.status).toBe(400);
    expect(res.body).toEqual({ detail: "malformed request body" });
  });
});
