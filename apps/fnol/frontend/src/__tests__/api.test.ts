import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getClaim, login, submitClaim } from "../lib/api";

/**
 * Single-seam test: every outbound fetch from FNOL's SPA must carry
 * `X-Source: prod`. This is the SPA half of the ADR-011 2026-06-07
 * amendment — the backend middleware default flipped to `unknown`, so
 * real UX traffic only lands in the `prod` bucket if the SPA tags it
 * explicitly. The fetch wrapper is the single seam; this test guards
 * against a future call site bypassing `request()` and forgetting it.
 */
describe("fetch wrapper — X-Source: prod single seam", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function lastHeaders(): Headers {
    const call = fetchSpy.mock.calls.at(-1);
    return (call?.[1] as RequestInit).headers as Headers;
  }

  it("login sends X-Source: prod", async () => {
    await login({ username: "alice", password: "x" });
    expect(lastHeaders().get("X-Source")).toBe("prod");
  });

  it("submitClaim sends X-Source: prod", async () => {
    await submitClaim(
      {
        policy_number: "POL-1",
        vehicle: { vin: "VIN-1", make: "M", model: "X", year: 2024 },
        incident: { occurred_at: "2026-01-01T00:00:00Z", description: "d" },
      } as never,
      "bearer",
    );
    expect(lastHeaders().get("X-Source")).toBe("prod");
  });

  it("getClaim sends X-Source: prod", async () => {
    await getClaim("CLM-1", "bearer");
    expect(lastHeaders().get("X-Source")).toBe("prod");
  });

  it("every recorded call across multiple endpoints carries X-Source: prod", async () => {
    await login({ username: "alice", password: "x" });
    await getClaim("CLM-1", "bearer");
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    for (const call of fetchSpy.mock.calls) {
      const headers = (call[1] as RequestInit).headers as Headers;
      expect(headers.get("X-Source")).toBe("prod");
    }
  });
});
