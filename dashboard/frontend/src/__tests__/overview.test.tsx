import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { Overview } from "../pages/Overview";
import type { StatusResponse } from "../types/logs";

const SAMPLE: StatusResponse = {
  as_of: "2026-06-04T16:30:00Z",
  apps: [
    {
      name: "shared-data-api",
      status: "ok",
      file_present: true,
      last_seen_at: "2026-06-04T16:29:55Z",
      counts_1h: { info: 1, warn: 0, error: 0 },
      counts_24h: { info: 1, warn: 0, error: 0 },
      counts_7d: { info: 1, warn: 0, error: 0 },
    },
    {
      name: "fnol",
      status: "degraded",
      file_present: true,
      last_seen_at: "2026-06-04T16:29:00Z",
      counts_1h: { info: 50, warn: 5, error: 12 },
      counts_24h: { info: 100, warn: 10, error: 15 },
      counts_7d: { info: 100, warn: 10, error: 15 },
    },
    {
      name: "customer-portal",
      status: "ok",
      file_present: true,
      last_seen_at: "2026-06-04T16:29:50Z",
      counts_1h: { info: 20, warn: 0, error: 0 },
      counts_24h: { info: 20, warn: 0, error: 0 },
      counts_7d: { info: 20, warn: 0, error: 0 },
    },
    {
      name: "agent-portal",
      status: "error",
      file_present: false,
      last_seen_at: null,
      counts_1h: { info: 0, warn: 0, error: 0 },
      counts_24h: { info: 0, warn: 0, error: 0 },
      counts_7d: { info: 0, warn: 0, error: 0 },
    },
  ],
};

function renderOverview() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Overview />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("dashboard_token", "test-token");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Overview", () => {
  it("renders one card per app once status loads", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(SAMPLE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderOverview();

    await waitFor(() => {
      expect(screen.getAllByTestId("status-card")).toHaveLength(4);
    });
    expect(screen.getByText("shared-data-api")).toBeInTheDocument();
    expect(screen.getByText("agent-portal")).toBeInTheDocument();
  });

  it("shows the error alert when the status request fails", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "boom" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderOverview();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /status request failed/,
    );
  });

  it("clears the token on a 401 so RequireAuth can bounce to /login", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid token" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderOverview();

    await waitFor(() => {
      expect(localStorage.getItem("dashboard_token")).toBeNull();
    });
  });
});
