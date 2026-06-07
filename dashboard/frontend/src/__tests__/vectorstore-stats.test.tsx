import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { VectorstoreStats } from "../pages/VectorstoreStats";
import type { ChromaStatsResponse } from "../types/vectorstore";

const POPULATED: ChromaStatsResponse = {
  total_count: 445,
  by_app: {
    fnol: 200,
    "shared-data-api": 170,
    "agent-portal": 40,
    "customer-portal": 35,
  },
  by_level: { WARN: 265, ERROR: 180 },
  by_source: { synthetic: 385, prod: 60 },
  by_event: [
    { event: "chaos_honored", count: 200 },
    { event: "login_failed", count: 50 },
    { event: "sda_upstream_rejected", count: 25 },
  ],
  by_day: [
    { date: "2026-06-04", count: 0 },
    { date: "2026-06-05", count: 100 },
    { date: "2026-06-06", count: 345 },
  ],
  embedding_model: "text-embedding-3-small",
  dimensions: 1536,
  as_of: "2026-06-06T22:50:00Z",
};

const EMPTY: ChromaStatsResponse = {
  total_count: 0,
  by_app: {},
  by_level: {},
  by_source: {},
  by_event: [],
  by_day: [{ date: "2026-06-06", count: 0 }],
  embedding_model: "text-embedding-3-small",
  dimensions: 1536,
  as_of: "2026-06-06T22:50:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <VectorstoreStats />
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

describe("VectorstoreStats", () => {
  it("renders summary cards + all five chart sections when populated", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(POPULATED), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Total embedded documents")).toBeInTheDocument();
    });
    // Summary cards
    expect(screen.getByText("445")).toBeInTheDocument();
    expect(screen.getByText("text-embedding-3-small")).toBeInTheDocument();
    expect(screen.getByText("1,536")).toBeInTheDocument();
    // Section headings (5 charts)
    expect(screen.getByText("By app")).toBeInTheDocument();
    expect(screen.getByText("By level")).toBeInTheDocument();
    expect(screen.getByText("By source")).toBeInTheDocument();
    expect(screen.getByText("Top events")).toBeInTheDocument();
    expect(screen.getByText("By day (last 7 days)")).toBeInTheDocument();
    // At least one bar from each section.
    expect(screen.getByText("fnol")).toBeInTheDocument();
    expect(screen.getByText("WARN")).toBeInTheDocument();
    expect(screen.getByText("synthetic")).toBeInTheDocument();
    expect(screen.getByText("chaos_honored")).toBeInTheDocument();
  });

  it("renders empty-corpus state with model info + a zero-filled day chart", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(EMPTY), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Total embedded documents")).toBeInTheDocument();
    });
    // The total-count summary card shows 0 (the by_day series ALSO renders a
    // "0" per zero-count day, so getByText("0") would be ambiguous). Anchor
    // on the summary card via the title attribute.
    expect(screen.getByTitle("0")).toBeInTheDocument();
    // The empty by_app section renders the configured emptyHint.
    expect(screen.getAllByText("No app data.").length).toBeGreaterThan(0);
  });

  it("renders the 503 unavailable banner when the vectorstore is missing", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Vectorstore unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/Vectorstore is unavailable/);
  });

  it("clears the token on 401 so RequireAuth bounces to /login", async () => {
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

  it("shows generic error banner on 500 response", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "boom" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/stats request failed/);
  });
});
