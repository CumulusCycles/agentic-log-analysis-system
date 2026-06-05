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
      user_id: "agent-1-uuid",
      role: "agent",
      app: "agent-portal",
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
  localStorage.setItem("agent_portal_token", makeTestToken());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClaimsPage", () => {
  it("renders all claims with status badge and customer id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify([
            {
              id: "c-1",
              policy_number: "POL-1004",
              customer_id: "alice-uuid",
              vin: "VIN-A",
              vehicle_snapshot: { make: "Toyota", model: "Camry", year: 2022 },
              incident_at: "2026-05-01T10:00:00Z",
              description: "rear-ended",
              current_status: "triaged",
              assigned_adjuster_id: null,
              created_at: "2026-05-01T10:05:00Z",
            },
            {
              id: "c-2",
              policy_number: "POL-1005",
              customer_id: "bob-uuid",
              vin: "VIN-B",
              vehicle_snapshot: { make: "Honda", model: "Civic", year: 2020 },
              incident_at: "2026-05-02T11:00:00Z",
              description: null,
              current_status: "investigating",
              assigned_adjuster_id: "agent-1-uuid",
              created_at: "2026-05-02T11:05:00Z",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderClaims();

    await waitFor(() => expect(screen.getByText("c-1")).toBeInTheDocument());
    expect(screen.getByText("c-2")).toBeInTheDocument();
    expect(screen.getByText("alice-uuid")).toBeInTheDocument();
    expect(screen.getByText("bob-uuid")).toBeInTheDocument();
    expect(screen.getAllByTestId("status-badge")).toHaveLength(2);
  });

  it("shows the empty-state message when there are no claims", async () => {
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
    expect(await screen.findByText(/no claims in the system/i)).toBeInTheDocument();
  });
});
