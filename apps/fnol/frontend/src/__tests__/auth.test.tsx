import { describe, expect, it } from "vitest";

import { decodeJwt } from "../lib/auth";

function base64urlEncode(s: string): string {
  return btoa(s).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function makeToken(payload: object): string {
  const header = base64urlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64urlEncode(JSON.stringify(payload));
  return `${header}.${body}.signature-not-verified-here`;
}

describe("decodeJwt", () => {
  it("decodes a well-formed JWT payload", () => {
    const payload = { user_id: "alice-id", role: "customer", app: "fnol" };
    const claims = decodeJwt(makeToken(payload));
    expect(claims).toEqual(payload);
  });

  it("decodes a payload whose base64url length is not a multiple of 4 (padding regression)", () => {
    const payload = { user_id: "y", app: "fnol" };
    const body = base64urlEncode(JSON.stringify(payload));
    // Confirm the precondition: this payload's base64url needs padding.
    // If a future change to the payload shape lands on a multiple of 4, this
    // assertion fails loudly so we know the regression case stopped exercising
    // the padding path.
    expect(body.length % 4).not.toBe(0);

    const claims = decodeJwt(makeToken(payload));
    expect(claims).toEqual(payload);
  });

  it("returns null for a malformed (non-three-segment) token", () => {
    expect(decodeJwt("only.twosegments")).toBeNull();
    expect(decodeJwt("not-a-jwt-at-all")).toBeNull();
    expect(decodeJwt("")).toBeNull();
  });
});
