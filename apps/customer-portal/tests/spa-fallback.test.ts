import request from "supertest";
import { describe, expect, it } from "vitest";

import { buildTestApp } from "./setup.js";

describe("SPA fallback / path traversal hardening", () => {
  it("never serves /etc/passwd contents for path-traversal attempts", async () => {
    const { express: app } = buildTestApp();
    for (const path of [
      "../etc/passwd",
      "../../etc/passwd",
      "..%2F..%2Fetc%2Fpasswd",
    ]) {
      const res = await request(app).get(`/${path}`);
      expect([200, 404]).toContain(res.status);
      // Only check file-contents leakage on 200 — Express's default 404
      // handler echoes the request path in its body, which is benign.
      if (res.status === 200) {
        expect(res.text ?? "").not.toMatch(/root:/);
        // /etc/passwd doesn't start with a `<` — index.html does.
        expect(res.text.trimStart().startsWith("<")).toBe(true);
      }
    }
  });

  it("returns 200 or 404 for any unknown SPA route", async () => {
    // In tests, frontend/dist may or may not exist. Either path is acceptable
    // as long as the response is well-formed (not a 500, not leaking files).
    const { express: app } = buildTestApp();
    const res = await request(app).get("/some-deep/spa-route");
    expect([200, 404]).toContain(res.status);
  });
});
