import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { Overview } from "../pages/Overview";
import type { StatusResponse } from "../types/logs";

function baseStatus(corpusEmpty: boolean | undefined): StatusResponse {
  return {
    as_of: "2026-06-05T12:00:00Z",
    apps: [
      {
        name: "shared-data-api",
        status: "ok",
        file_present: true,
        last_seen_at: "2026-06-05T11:59:55Z",
        counts_1h: { info: 1, warn: 0, error: 0 },
        counts_24h: { info: 1, warn: 0, error: 0 },
        counts_7d: { info: 1, warn: 0, error: 0 },
      },
      {
        name: "fnol",
        status: "ok",
        file_present: true,
        last_seen_at: "2026-06-05T11:59:55Z",
        counts_1h: { info: 1, warn: 0, error: 0 },
        counts_24h: { info: 1, warn: 0, error: 0 },
        counts_7d: { info: 1, warn: 0, error: 0 },
      },
      {
        name: "customer-portal",
        status: "ok",
        file_present: true,
        last_seen_at: "2026-06-05T11:59:55Z",
        counts_1h: { info: 1, warn: 0, error: 0 },
        counts_24h: { info: 1, warn: 0, error: 0 },
        counts_7d: { info: 1, warn: 0, error: 0 },
      },
      {
        name: "agent-portal",
        status: "ok",
        file_present: true,
        last_seen_at: "2026-06-05T11:59:55Z",
        counts_1h: { info: 1, warn: 0, error: 0 },
        counts_24h: { info: 1, warn: 0, error: 0 },
        counts_7d: { info: 1, warn: 0, error: 0 },
      },
    ],
    corpus_empty: corpusEmpty,
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

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

describe("Overview empty-corpus banner", () => {
  it("shows the banner when corpus_empty=true with a Log Generator link", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(baseStatus(true))));

    renderOverview();

    await waitFor(() => {
      expect(screen.getByTestId("empty-corpus-banner")).toBeInTheDocument();
    });
    const link = screen.getByRole("link", { name: /open log generator/i });
    expect(link).toHaveAttribute("href", "/log-generator");
  });

  it("hides the banner when corpus_empty=false", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(baseStatus(false))));

    renderOverview();

    await waitFor(() => {
      expect(screen.getAllByTestId("status-card").length).toBeGreaterThan(0);
    });
    expect(screen.queryByTestId("empty-corpus-banner")).not.toBeInTheDocument();
  });

  it("hides the banner when corpus_empty is absent (backwards compat)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(baseStatus(undefined))));

    renderOverview();

    await waitFor(() => {
      expect(screen.getAllByTestId("status-card").length).toBeGreaterThan(0);
    });
    expect(screen.queryByTestId("empty-corpus-banner")).not.toBeInTheDocument();
  });
});
