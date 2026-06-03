import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { ClaimsPage } from "../pages/ClaimsPage";

function makeTestToken(): string {
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

function renderClaims() {
  return render(
    <MemoryRouter initialEntries={["/claims"]}>
      <AuthProvider>
        <ClaimsPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("customer_portal_token", makeTestToken());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClaimsPage", () => {
  it("renders claim cards including the status badge", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify([
            {
              id: "c-1",
              policy_number: "POL-1004",
              customer_id: "u-1",
              vin: "VIN-A",
              vehicle_snapshot: { make: "Toyota", model: "Camry", year: 2022 },
              incident_at: "2026-05-01T10:00:00Z",
              description: "fender bender",
              current_status: "triaged",
              assigned_adjuster_id: null,
              created_at: "2026-05-01T10:05:00Z",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderClaims();

    await waitFor(() => expect(screen.getByText("c-1")).toBeInTheDocument());
    expect(screen.getByText("POL-1004")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveTextContent("triaged");
    expect(screen.getByText(/fender bender/i)).toBeInTheDocument();
  });

  it("shows the empty-state message when the customer has no claims", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    renderClaims();
    expect(await screen.findByText(/no claims filed/i)).toBeInTheDocument();
  });
});
