import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { LogGenerator } from "../pages/LogGenerator";
import type { RunRecord, ScenarioSpec } from "../types/agitator";

const SCENARIOS: ScenarioSpec[] = [
  {
    name: "auth-spike",
    display_name: "Auth spike",
    description: "50 failed FNOL logins over 30 seconds.",
    target_app: "fnol",
    requires_chaos: false,
    params: [
      { name: "count", minimum: 1, maximum: 500, default: 50 },
      { name: "duration_s", minimum: 1, maximum: 300, default: 30 },
    ],
  },
  {
    name: "sda-degraded",
    display_name: "SDA degraded",
    description: "240 SDA reads with X-Chaos: slow:500 over 120s.",
    target_app: "shared-data-api",
    requires_chaos: true,
    params: [
      { name: "count", minimum: 1, maximum: 1000, default: 240 },
      { name: "duration_s", minimum: 1, maximum: 600, default: 120 },
    ],
  },
];

function runRecord(over: Partial<RunRecord> = {}): RunRecord {
  return {
    run_id: over.run_id ?? "r1",
    scenario: over.scenario ?? "auth-spike",
    params: over.params ?? { count: 50, duration_s: 30 },
    state: over.state ?? "running",
    started_at: over.started_at ?? "2026-06-05T12:00:00Z",
    ended_at: over.ended_at ?? null,
    sent: over.sent ?? 0,
    succeeded: over.succeeded ?? 0,
    failed: over.failed ?? 0,
    last_status_code: over.last_status_code ?? null,
    last_error: over.last_error ?? null,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LogGenerator />
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

describe("LogGenerator", () => {
  it("renders one card per scenario from the API", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: false }));
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("scenario-card-auth-spike")).toBeInTheDocument();
      expect(screen.getByTestId("scenario-card-sda-degraded")).toBeInTheDocument();
    });
  });

  it("disables sda-degraded when ENABLE_CHAOS=false", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: false }));
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      const sdaButton = screen.getByTestId("run-button-sda-degraded") as HTMLButtonElement;
      expect(sdaButton.disabled).toBe(true);
      const authButton = screen.getByTestId("run-button-auth-spike") as HTMLButtonElement;
      expect(authButton.disabled).toBe(false);
    });
    expect(screen.getByTestId("chaos-disabled-note")).toBeInTheDocument();
  });

  it("enables sda-degraded when ENABLE_CHAOS=true", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: true }));
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      const sdaButton = screen.getByTestId("run-button-sda-degraded") as HTMLButtonElement;
      expect(sdaButton.disabled).toBe(false);
    });
    expect(screen.queryByTestId("chaos-disabled-note")).not.toBeInTheDocument();
  });

  it("POSTs to /api/agitator/runs when Run is clicked", async () => {
    const started = runRecord({ state: "running", sent: 0 });
    const fetchSpy = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: false }));
      if (url.endsWith("/api/agitator/runs") && init?.method === "POST") {
        return Promise.resolve(jsonResponse(started, 201));
      }
      if (url.includes("/runs")) {
        return Promise.resolve(jsonResponse({ runs: [started] }));
      }
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => expect(screen.getByTestId("scenario-card-auth-spike")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("run-button-auth-spike"));

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.endsWith("/api/agitator/runs"))).toBe(true);
    });
  });

  it("shows a cancel button on running runs and POSTs to cancel", async () => {
    const running = runRecord({ state: "running", sent: 5 });
    const cancelled = runRecord({ state: "cancelled", sent: 5 });
    let cancelCalled = false;
    const fetchSpy = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: false }));
      if (url.endsWith("/cancel") && init?.method === "POST") {
        cancelCalled = true;
        return Promise.resolve(jsonResponse(cancelled));
      }
      if (url.includes("/runs")) {
        return Promise.resolve(jsonResponse({ runs: cancelCalled ? [cancelled] : [running] }));
      }
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId(`cancel-button-${running.run_id}`)).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByTestId(`cancel-button-${running.run_id}`));

    await waitFor(() => expect(cancelCalled).toBe(true));
  });

  it("clears token on 401 from initial load", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid token" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      expect(localStorage.getItem("dashboard_token")).toBeNull();
    });
  });

  it("surfaces a 409 from start as an error banner", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: false }));
      if (url.endsWith("/api/agitator/runs") && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ detail: "auth-spike is already running" }, 409));
      }
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => expect(screen.getByTestId("scenario-card-auth-spike")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("run-button-auth-spike"));

    await waitFor(() => {
      expect(screen.getByTestId("error-banner")).toHaveTextContent(/already running/);
    });
  });

  // --- PR 3: per-card recent runs + standalone panel removed ---

  it("renders each run inside its own scenario card (and not in others)", async () => {
    const authRunning = runRecord({
      run_id: "auth-r1",
      scenario: "auth-spike",
      state: "running",
      sent: 7,
      succeeded: 5,
      failed: 2,
    });
    const authSucceeded = runRecord({
      run_id: "auth-r2",
      scenario: "auth-spike",
      state: "succeeded",
      sent: 50,
      succeeded: 50,
      failed: 0,
      started_at: "2026-06-05T11:50:00Z",
    });
    const sdaFailed = runRecord({
      run_id: "sda-r1",
      scenario: "sda-degraded",
      state: "failed",
      sent: 240,
      succeeded: 100,
      failed: 140,
    });

    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: true }));
      if (url.includes("/runs")) {
        return Promise.resolve(jsonResponse({ runs: [authRunning, authSucceeded, sdaFailed] }));
      }
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    // Wait for per-card scoping to materialise. Each card has its own
    // `scenario-runs-<name>` block — the auth card lists 2 rows; sda has 1.
    await waitFor(() => {
      const authCard = screen.getByTestId("scenario-runs-auth-spike");
      expect(authCard.querySelectorAll('[data-testid^="run-row-"]').length).toBe(2);
      const sdaCard = screen.getByTestId("scenario-runs-sda-degraded");
      expect(sdaCard.querySelectorAll('[data-testid^="run-row-"]').length).toBe(1);
    });

    // The auth card never shows the sda run, and vice versa.
    const authCard = screen.getByTestId("scenario-runs-auth-spike");
    expect(authCard.querySelector('[data-testid="run-row-sda-r1"]')).toBeNull();
    const sdaCard = screen.getByTestId("scenario-runs-sda-degraded");
    expect(sdaCard.querySelector('[data-testid="run-row-auth-r1"]')).toBeNull();
  });

  it("shows an empty-state hint inside a card with zero runs", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: true }));
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      const authCard = screen.getByTestId("scenario-runs-auth-spike");
      expect(authCard).toHaveTextContent(/no runs yet/i);
    });
  });

  it("no longer renders the standalone Recent runs panel", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: false }));
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => expect(screen.getByTestId("scenario-card-auth-spike")).toBeInTheDocument());

    // The old global `recent-runs` panel test id is gone — replaced by
    // per-card `scenario-runs-*` containers.
    expect(screen.queryByTestId("recent-runs")).toBeNull();
  });

  it("scenario cards declare the uniform min-height class", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: true }));
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      // Every card carries the same min-h-[320px] + flex-col classes so
      // the grid lays out evenly regardless of description length or
      // run-history density. jsdom doesn't compute styles, so we assert
      // the class membership instead of measured heights.
      for (const spec of SCENARIOS) {
        const card = screen.getByTestId(`scenario-card-${spec.name}`);
        expect(card.className).toMatch(/min-h-\[320px\]/);
        expect(card.className).toMatch(/flex-col/);
      }
    });
  });

  it("caps the per-card run list at 5 even when more exist", async () => {
    const manyRuns: RunRecord[] = Array.from({ length: 8 }, (_, i) =>
      runRecord({
        run_id: `auth-r${i}`,
        scenario: "auth-spike",
        state: "succeeded",
        // Decreasing timestamps so the newest is r0 and the oldest is r7.
        started_at: new Date(2026, 5, 5, 12, 0, 0, -i * 1000).toISOString(),
      }),
    );
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/env")) return Promise.resolve(jsonResponse({ enable_chaos: false }));
      if (url.includes("/runs")) return Promise.resolve(jsonResponse({ runs: manyRuns }));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      const authCard = screen.getByTestId("scenario-runs-auth-spike");
      expect(authCard.querySelectorAll('[data-testid^="run-row-"]').length).toBe(5);
    });
  });
});
