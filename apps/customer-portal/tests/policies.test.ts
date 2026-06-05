import nock from "nock";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { buildTestApp, makeToken, TEST_CONFIG } from "./setup.js";

describe("GET /policies/me", () => {
  it("returns the SDA policies array filtered by customer_id", async () => {
    const token = makeToken({ user_id: "u-1" });
    const scope = nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/policies")
      .query({ customer_id: "u-1" })
      .reply(200, [
        {
          policy_number: "POL-1004",
          customer_id: "u-1",
          effective_date: "2025-01-01",
          expiration_date: "2026-01-01",
          coverage_type: "auto-comprehensive",
          premium_cents: 120000,
          vehicles: [{ vin: "VIN-1", make: "Toyota", model: "Camry", year: 2022 }],
        },
      ]);

    const { express: app } = buildTestApp();
    const res = await request(app).get("/policies/me").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    expect(res.body[0].policy_number).toBe("POL-1004");
    expect(res.body[0].vehicles[0].vin).toBe("VIN-1");
    scope.done();
  });

  it("returns an empty array when SDA reports the customer has no policies", async () => {
    const token = makeToken({ user_id: "u-2" });
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/policies")
      .query({ customer_id: "u-2" })
      .reply(200, []);

    const { express: app } = buildTestApp();
    const res = await request(app).get("/policies/me").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it("requires a bearer token", async () => {
    const { express: app } = buildTestApp();
    const res = await request(app).get("/policies/me");
    expect(res.status).toBe(401);
  });

  it("passes a 500 from SDA back to the client", async () => {
    const token = makeToken();
    nock(TEST_CONFIG.SHARED_DATA_API_BASE_URL)
      .get("/policies")
      .query(true)
      .reply(500, { detail: "boom" });

    const { express: app } = buildTestApp();
    const res = await request(app).get("/policies/me").set("Authorization", `Bearer ${token}`);

    expect(res.status).toBe(500);
    expect(res.body).toEqual({ detail: "boom" });
  });
});
