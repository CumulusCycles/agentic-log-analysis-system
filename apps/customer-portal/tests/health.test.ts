import request from "supertest";
import { describe, expect, it } from "vitest";

import { buildTestApp } from "./setup.js";

describe("GET /health", () => {
  it("returns 200 with status ok", async () => {
    const { express: app } = buildTestApp();
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: "ok" });
  });
});
