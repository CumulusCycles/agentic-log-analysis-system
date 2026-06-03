import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { ClaimDetailPage } from "../pages/ClaimDetailPage";

function seedToken() {
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

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/claims/claim-1"]}>
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
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClaimDetailPage", () => {
  it("fetches and renders status + history once the API responds", async () => {
    seedToken();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "claim-1",
            policy_number: "POL-1004",
            customer_id: "cust-42",
            vin: "VIN12345678901234",
            incident_at: "2026-06-01T10:00:00Z",
            description: "rear-ended at intersection",
            current_status: "triaged",
            assigned_adjuster_id: "agent-1",
            created_at: "2026-06-03T00:00:00Z",
            history: [
              {
                from_status: "submitted",
                to_status: "triaged",
                actor_id: "system",
                changed_at: "2026-06-03T00:01:00Z",
                note: null,
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderDetail();

    // Wait for the status <dd> (sibling of "Status" <dt>) to render with "triaged".
    const statusValue = await screen.findByText("triaged", { selector: "dd" });
    expect(statusValue).toBeInTheDocument();
    expect(screen.getByText("POL-1004")).toBeInTheDocument();
    expect(screen.getByText("VIN12345678901234")).toBeInTheDocument();
    expect(screen.getByText(/rear-ended at intersection/i)).toBeInTheDocument();
  });

  it("shows an error alert when the API returns 404", async () => {
    seedToken();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "claim not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    renderDetail();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "claim not found",
    );
  });
});
