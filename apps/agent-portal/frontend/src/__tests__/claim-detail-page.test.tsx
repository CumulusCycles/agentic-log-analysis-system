import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { ClaimDetailPage } from "../pages/ClaimDetailPage";

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

function renderDetail(claimId: string) {
  return render(
    <MemoryRouter initialEntries={[`/claims/${claimId}`]}>
      <AuthProvider>
        <Routes>
          <Route path="/claims/:id" element={<ClaimDetailPage />} />
        </Routes>
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

describe("ClaimDetailPage", () => {
  it("renders the claim and its status history timeline", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "c-1",
            policy_number: "POL-1004",
            customer_id: "alice-uuid",
            vin: "VIN-A",
            vehicle_snapshot: { make: "Toyota", model: "Camry", year: 2022 },
            incident_at: "2026-05-01T10:00:00Z",
            description: "rear-ended at low speed",
            current_status: "investigating",
            assigned_adjuster_id: "agent-1-uuid",
            created_at: "2026-05-01T10:05:00Z",
            history: [
              {
                from_status: null,
                to_status: "submitted",
                actor_id: "system",
                changed_at: "2026-05-01T10:05:00Z",
                note: null,
              },
              {
                from_status: "submitted",
                to_status: "investigating",
                actor_id: "system",
                changed_at: "2026-05-01T10:15:00Z",
                note: "auto-assigned",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderDetail("c-1");

    await waitFor(() => expect(screen.getByText("c-1")).toBeInTheDocument());
    expect(screen.getByText("POL-1004")).toBeInTheDocument();
    expect(screen.getByText(/rear-ended at low speed/i)).toBeInTheDocument();
    expect(screen.getByTestId("status-timeline")).toBeInTheDocument();
    expect(screen.getByText(/submitted → investigating/i)).toBeInTheDocument();
    expect(screen.getByText(/auto-assigned/i)).toBeInTheDocument();
  });

  it("handles an empty history list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "c-2",
            policy_number: "POL-1005",
            customer_id: "bob-uuid",
            vin: "VIN-B",
            vehicle_snapshot: null,
            incident_at: "2026-05-02T11:00:00Z",
            description: null,
            current_status: "submitted",
            assigned_adjuster_id: null,
            created_at: "2026-05-02T11:05:00Z",
            history: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderDetail("c-2");
    await waitFor(() => expect(screen.getByText("c-2")).toBeInTheDocument());
    expect(screen.getByText(/no status history/i)).toBeInTheDocument();
  });
});
