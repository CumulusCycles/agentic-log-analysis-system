import nock from "nock";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { buildTestApp, makeToken, TEST_CONFIG } from "./setup.js";

describe("GET /claims/me", () => {
  it("returns the SDA claims array filtered by customer_id", async () => {
    const token = makeToken({ user_id: "u-1" });
    const scope = nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/claims")
      .query({ customer_id: "u-1" })
      .reply(200, [
        {
          id: "c-1",
          policy_number: "POL-1004",
          customer_id: "u-1",
          vin: "VIN-1",
          vehicle_snapshot: { make: "Toyota", model: "Camry", year: 2022 },
          incident_at: "2026-05-01T10:00:00Z",
          description: "scratch",
          current_status: "submitted",
          assigned_adjuster_id: null,
          created_at: "2026-05-01T10:05:00Z",
        },
      ]);

    const { express: app } = buildTestApp();
    const res = await request(app).get("/claims/me").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    expect(res.body[0].id).toBe("c-1");
    expect(res.body[0].current_status).toBe("submitted");
    scope.done();
  });

  it("returns an empty array when SDA reports no claims", async () => {
    const token = makeToken({ user_id: "u-3" });
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/claims")
      .query({ customer_id: "u-3" })
      .reply(200, []);

    const { express: app } = buildTestApp();
    const res = await request(app).get("/claims/me").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it("requires a bearer token", async () => {
    const { express: app } = buildTestApp();
    const res = await request(app).get("/claims/me");
    expect(res.status).toBe(401);
  });

  it("returns 502 when SDA is unreachable", async () => {
    const token = makeToken();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/claims")
      .query(true)
      .replyWithError({ code: "ECONNREFUSED", message: "boom" });

    const { express: app } = buildTestApp();
    const res = await request(app).get("/claims/me").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(502);
  });
});
