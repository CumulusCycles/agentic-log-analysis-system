import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { SubmitClaimPage } from "../pages/SubmitClaimPage";

// Pre-seed a token whose payload decodes to a known user_id.
function seedToken() {
  // header.payload.sig — payload = { user_id: "cust-42", app: "fnol", role: "customer" }
  const payload = btoa(
    JSON.stringify({
      iss: "shared-data-api",
      aud: "agentic-log-analysis-insurance-apps",
      user_id: "cust-42",
      role: "customer",
      app: "fnol",
      iat: 1,
      exp: 9_999_999_999,
    }),
  )
    .replace(/=+$/, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  localStorage.setItem("fnol_token", `head.${payload}.sig`);
}

function renderSubmit() {
  return render(
    <MemoryRouter initialEntries={["/submit"]}>
      <AuthProvider>
        <SubmitClaimPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SubmitClaimPage", () => {
  it("renders the four required fields with their labels", () => {
    seedToken();
    renderSubmit();
    expect(screen.getByLabelText(/policy number/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/vin/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/incident date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/what happened/i)).toBeInTheDocument();
  });

  it("posts to /fnol/submit with the customer_id derived from the JWT", async () => {
    seedToken();
    let captured: { url: string; init: RequestInit } | null = null;
    const fetchSpy = vi.fn(async (url: string, init: RequestInit) => {
      captured = { url, init };
      return new Response(
        JSON.stringify({
          id: "claim-1",
          policy_number: "POL-1004",
          customer_id: "cust-42",
          vin: "VIN12345678901234",
          incident_at: "2026-06-01T10:00",
          description: "ouch",
          current_status: "submitted",
          assigned_adjuster_id: null,
          created_at: "2026-06-03T00:00:00Z",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderSubmit();
    await userEvent.type(screen.getByLabelText(/policy number/i), "POL-1004");
    await userEvent.type(screen.getByLabelText(/vin/i), "VIN12345678901234");
    await userEvent.type(
      screen.getByLabelText(/incident date/i),
      "2026-06-01T10:00",
    );
    await userEvent.type(screen.getByLabelText(/what happened/i), "ouch");
    await userEvent.click(
      screen.getByRole("button", { name: /submit claim/i }),
    );

    expect(fetchSpy).toHaveBeenCalled();
    const seen = captured as unknown as {
      url: string;
      init: RequestInit;
    } | null;
    if (!seen) throw new Error("fetch was not called");
    const body = JSON.parse(seen.init.body as string);
    expect(body.customer_id).toBe("cust-42");
    expect(body.policy_number).toBe("POL-1004");
    expect(seen.url).toContain("/fnol/submit");
  });
});
