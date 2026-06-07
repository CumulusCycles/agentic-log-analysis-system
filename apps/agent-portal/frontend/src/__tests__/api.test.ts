import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getClaim, getClaims, getProfile, login } from "../lib/api";

/**
 * Single-seam test: every outbound fetch from Agent Portal's SPA must
 * carry `X-Source: prod`. ADR-011 2026-06-07 amendment — the backend
 * middleware default flipped to `unknown`, so real UX traffic only lands
 * in the `prod` bucket if the SPA tags it explicitly. The fetch wrapper
 * is the single seam.
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
    await login({ username: "agent1", password: "x" });
    expect(lastHeaders().get("X-Source")).toBe("prod");
  });

  it("getProfile sends X-Source: prod", async () => {
    await getProfile("bearer");
    expect(lastHeaders().get("X-Source")).toBe("prod");
  });

  it("getClaims sends X-Source: prod", async () => {
    await getClaims("bearer");
    expect(lastHeaders().get("X-Source")).toBe("prod");
  });

  it("getClaim sends X-Source: prod", async () => {
    await getClaim("bearer", "c42");
    expect(lastHeaders().get("X-Source")).toBe("prod");
  });

  it("every recorded call across multiple endpoints carries X-Source: prod", async () => {
    await login({ username: "agent1", password: "x" });
    await getClaims("bearer");
    await getClaim("bearer", "c42");
    await getProfile("bearer");
    expect(fetchSpy).toHaveBeenCalledTimes(4);
    for (const call of fetchSpy.mock.calls) {
      const headers = (call[1] as RequestInit).headers as Headers;
      expect(headers.get("X-Source")).toBe("prod");
    }
  });
});
