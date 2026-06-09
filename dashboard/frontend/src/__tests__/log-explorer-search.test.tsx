import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { LogExplorer } from "../pages/LogExplorer";
import type { LogEntry, LogsResponse, LogsSearchResponse } from "../types/logs";

function entry(over: Partial<LogEntry> = {}): LogEntry {
  return {
    id: over.id ?? "fnol:1",
    timestamp: over.timestamp ?? "2026-06-04T16:30:00Z",
    level: over.level ?? "INFO",
    app: over.app ?? "fnol",
    event: over.event ?? "claim_submitted",
    fields: over.fields ?? {},
    raw: over.raw ?? "raw line",
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderExplorer() {
  return render(
    <MemoryRouter initialEntries={["/logs"]}>
      <AuthProvider>
        <LogExplorer />
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

describe("LogExplorer (7d semantic search)", () => {
  it("typing in the search box switches to POST /api/logs/search after debounce", async () => {
    const logsResp: LogsResponse = { entries: [], next_before: null };
    const searchResp: LogsSearchResponse = {
      entries: [entry({ id: "fnol:99", event: "auth_failed" })],
      scores: [0.87],
    };
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(logsResp))
      .mockResolvedValueOnce(jsonResponse(searchResp));
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();

    // First call is /api/logs.
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    expect(String(fetchSpy.mock.calls[0][0])).toMatch(/\/api\/logs\?/);

    await userEvent.type(screen.getByTestId("filter-query"), "auth failure");

    await waitFor(
      () => {
        const lastCall = fetchSpy.mock.calls.at(-1);
        expect(String(lastCall?.[0])).toMatch(/\/api\/logs\/search$/);
      },
      { timeout: 2000 },
    );
    const searchCall = fetchSpy.mock.calls.at(-1);
    expect(searchCall?.[1]?.method).toBe("POST");
    expect(JSON.parse(searchCall?.[1]?.body as string)).toMatchObject({
      query: "auth failure",
    });
  });

  it("falls back to /api/logs when the search input is cleared", async () => {
    const logsResp: LogsResponse = { entries: [], next_before: null };
    const searchResp: LogsSearchResponse = { entries: [], scores: [] };
    const fetchSpy = vi.fn().mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes("/api/logs/search")) {
        return Promise.resolve(jsonResponse(searchResp));
      }
      return Promise.resolve(jsonResponse(logsResp));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();
    await userEvent.type(screen.getByTestId("filter-query"), "x");
    await waitFor(
      () => {
        const last = fetchSpy.mock.calls.at(-1);
        expect(String(last?.[0])).toMatch(/\/api\/logs\/search/);
      },
      { timeout: 2000 },
    );

    await userEvent.clear(screen.getByTestId("filter-query"));
    await waitFor(
      () => {
        const last = fetchSpy.mock.calls.at(-1);
        expect(String(last?.[0])).toMatch(/\/api\/logs\?/);
      },
      { timeout: 2000 },
    );
  });

  it("renders a score column when search results carry scores", async () => {
    const searchResp: LogsSearchResponse = {
      entries: [
        entry({ id: "fnol:1", event: "auth_failed" }),
        entry({ id: "fnol:2", event: "auth_failed" }),
      ],
      scores: [0.91, 0.78],
    };
    const logsResp: LogsResponse = { entries: [], next_before: null };
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(logsResp))
      .mockResolvedValue(jsonResponse(searchResp));
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();
    await userEvent.type(screen.getByTestId("filter-query"), "auth");

    await waitFor(
      () => {
        expect(screen.getByTestId("score-header")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
    const cells = screen.getAllByTestId("score-cell");
    expect(cells[0]).toHaveTextContent("0.910");
    expect(cells[1]).toHaveTextContent("0.780");
  });

  it("shows a friendly error when /api/logs/search returns 503", async () => {
    const logsResp: LogsResponse = { entries: [], next_before: null };
    const fetchSpy = vi.fn().mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes("/api/logs/search")) {
        return Promise.resolve(errorResponse(503, "semantic search is unavailable"));
      }
      return Promise.resolve(jsonResponse(logsResp));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();
    await userEvent.type(screen.getByTestId("filter-query"), "auth");

    expect(await screen.findByRole("alert")).toHaveTextContent(/OLLAMA_BASE_URL/i);
  });

  it("renders the partial-corpus hint when the search response says backfill is still running", async () => {
    // v1.1.2 — the backend reports `partial_corpus: true` while the
    // lifespan backfill is still populating Chroma. The Log Explorer
    // shows an inline "indexing in progress" hint so empty / sparse
    // results during cold-start don't read as "no matches".
    const logsResp: LogsResponse = { entries: [], next_before: null };
    const searchResp: LogsSearchResponse = {
      entries: [entry({ id: "fnol:1", event: "auth_failed" })],
      scores: [0.5],
      partial_corpus: true,
    };
    const fetchSpy = vi.fn().mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes("/api/logs/search")) {
        return Promise.resolve(jsonResponse(searchResp));
      }
      return Promise.resolve(jsonResponse(logsResp));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();
    await userEvent.type(screen.getByTestId("filter-query"), "auth");

    const hint = await screen.findByTestId("partial-corpus-hint");
    expect(hint).toHaveTextContent(/indexing/i);
  });

  it("does not render the partial-corpus hint when the search response is complete", async () => {
    // Inverse of the previous test — the hint MUST NOT leak into the
    // steady-state UI. `partial_corpus: false` (or absent) keeps the
    // panel clean.
    const logsResp: LogsResponse = { entries: [], next_before: null };
    const searchResp: LogsSearchResponse = {
      entries: [entry({ id: "fnol:1", event: "auth_failed" })],
      scores: [0.5],
      partial_corpus: false,
    };
    const fetchSpy = vi.fn().mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes("/api/logs/search")) {
        return Promise.resolve(jsonResponse(searchResp));
      }
      return Promise.resolve(jsonResponse(logsResp));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();
    await userEvent.type(screen.getByTestId("filter-query"), "auth");

    // Wait for the score column so we know the search response landed.
    await screen.findByTestId("score-header");
    expect(screen.queryByTestId("partial-corpus-hint")).toBeNull();
  });

  it("renders the partial-corpus hint with EMPTY results — the cold-start UX case", async () => {
    // v1.1.2 post-review — the most operator-confusing scenario:
    // partial_corpus: true AND entries: []. Without the hint, the
    // empty-state would read as "no matches" when the truth is
    // "still indexing." This test pins the cold-start UX explicitly.
    const logsResp: LogsResponse = { entries: [], next_before: null };
    const searchResp: LogsSearchResponse = {
      entries: [],
      scores: [],
      partial_corpus: true,
    };
    const fetchSpy = vi.fn().mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes("/api/logs/search")) {
        return Promise.resolve(jsonResponse(searchResp));
      }
      return Promise.resolve(jsonResponse(logsResp));
    });
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();
    await userEvent.type(screen.getByTestId("filter-query"), "auth");

    const hint = await screen.findByTestId("partial-corpus-hint");
    expect(hint).toBeInTheDocument();
    expect(hint).toHaveTextContent(/indexing/i);
  });
});
