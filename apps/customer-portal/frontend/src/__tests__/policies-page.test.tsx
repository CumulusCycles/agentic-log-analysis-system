import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { PoliciesPage } from "../pages/PoliciesPage";

const SEED_TOKEN = makeTestToken();

function makeTestToken(): string {
  // Hand-rolled JWT — never verified client-side, just decoded for user_id.
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({
      iss: "shared-data-api",
      aud: "agentic-log-analysis-insurance-apps",
      user_id: "u-1",
      role: "customer",
      app: "customer-portal",
      iat: 0,
      exp: 9999999999,
    }),
  );
  return `${header}.${payload}.sig`;
}

function renderPolicies() {
  return render(
    <MemoryRouter initialEntries={["/policies"]}>
      <AuthProvider>
        <PoliciesPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("customer_portal_token", SEED_TOKEN);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PoliciesPage", () => {
  it("renders policy cards returned by the API", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            policy_number: "POL-1004",
            customer_id: "u-1",
            effective_date: "2025-01-01",
            expiration_date: "2026-01-01",
            coverage_type: "auto-comprehensive",
            premium_cents: 120000,
            vehicles: [{ vin: "VIN-A", make: "Toyota", model: "Camry", year: 2022 }],
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPolicies();

    await waitFor(() => expect(screen.getByText("POL-1004")).toBeInTheDocument());
    expect(screen.getByText(/Toyota/)).toBeInTheDocument();
    expect(screen.getByText(/VIN-A/)).toBeInTheDocument();
    expect(screen.getByText(/auto-comprehensive/)).toBeInTheDocument();
  });

  it("shows the empty-state message when the customer has no policies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    renderPolicies();
    expect(await screen.findByText(/no policies on file/i)).toBeInTheDocument();
  });
});
