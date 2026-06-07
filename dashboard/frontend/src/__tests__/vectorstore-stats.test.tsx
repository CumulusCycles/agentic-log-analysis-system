import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("VectorstoreStats — flush panel", () => {
  it("disables the flush button when the corpus is empty", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(EMPTY), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();

    const btn = await screen.findByTestId("flush-button");
    expect(btn).toBeDisabled();
  });

  it("shows the confirmation dialog with cost estimate when Flush is clicked", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(POPULATED), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();
    const btn = await screen.findByTestId("flush-button");
    fireEvent.click(btn);

    const dialog = await screen.findByTestId("flush-confirm");
    expect(dialog).toHaveTextContent(/Delete all 445 embedded documents/);
    // 445 docs × 80 tokens × $0.02/1M ≈ $0.000712 → "less than $0.01"
    expect(dialog).toHaveTextContent(/less than \$0\.01/);
    expect(dialog).toHaveTextContent(/docker compose restart log-dashboard/);
  });

  it("cancels back to the panel when Cancel is clicked", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(POPULATED), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();
    fireEvent.click(await screen.findByTestId("flush-button"));
    fireEvent.click(await screen.findByTestId("flush-cancel-button"));

    expect(screen.queryByTestId("flush-confirm")).not.toBeInTheDocument();
    expect(screen.getByTestId("flush-button")).toBeEnabled();
  });

  it("posts to /api/chroma/flush and shows a result banner on success", async () => {
    let postCalls = 0;
    const fetchSpy = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/api/chroma/flush")) {
        postCalls += 1;
        return Promise.resolve(
          new Response(JSON.stringify({ deleted_count: 445, as_of: "2026-06-07T00:00:00Z" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify(POPULATED), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();
    fireEvent.click(await screen.findByTestId("flush-button"));
    fireEvent.click(await screen.findByTestId("flush-confirm-button"));

    const result = await screen.findByTestId("flush-result");
    expect(result).toHaveTextContent(/Deleted 445 documents/);
    expect(result).toHaveTextContent(/docker compose restart log-dashboard/);
    expect(postCalls).toBe(1);
  });

  it("renders an error banner when the flush call fails", async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/api/chroma/flush")) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Vectorstore unavailable" }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify(POPULATED), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderPage();
    fireEvent.click(await screen.findByTestId("flush-button"));
    fireEvent.click(await screen.findByTestId("flush-confirm-button"));

    const banner = await screen.findByTestId("flush-error");
    expect(banner).toHaveTextContent(/flush failed \(503\)/);
  });
});
