import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { ErrorDetail } from "../pages/ErrorDetail";
import type { ErrorDetailResponse } from "../types/errors";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function detailBody(over: Partial<ErrorDetailResponse> = {}): ErrorDetailResponse {
  return {
    entry: {
      id: "fnol:aaaa111122223333",
      timestamp: "2026-06-05T10:00:00Z",
      level: "ERROR",
      app: "fnol",
      event: "request_failed",
      fields: { caller: "fnol", status: 500, claim_id: "C-101" },
      raw: 'ERROR fnol request_failed claim_id="C-101"',
    },
    analysis: {
      answer: "Likely a downstream Shared Data API failure.",
      citations: [],
      dry_run: true,
      tool_budget_exhausted: false,
    },
    ...over,
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/errors/:id" element={<ErrorDetail />} />
        </Routes>
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

describe("ErrorDetail", () => {
  it("renders the entry meta and the Suggested Fix answer", async () => {
    const body = detailBody();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(body)));

    renderAt("/errors/fnol:aaaa111122223333");

    expect(screen.getByRole("status")).toHaveTextContent(/loading/i);

    await waitFor(() => expect(screen.getByText(/Likely a downstream/i)).toBeInTheDocument());

    // Entry meta — multiple "fnol" matches (badge + fields dd), assert the count
    // and the level pill via testid so the assertion is unambiguous.
    expect(screen.getAllByText("fnol").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId("level-pill")).toHaveAttribute("data-level", "ERROR");
    // The raw line is rendered verbatim in a <pre> block.
    expect(screen.getByText(/request_failed claim_id/)).toBeInTheDocument();
    // DRY RUN banner from analysis.dry_run=true
    expect(screen.getByText("DRY RUN")).toBeInTheDocument();
  });

  it("shows a 404 friendly message when the entry is not in Chroma", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "entry not found" }, 404)),
    );

    renderAt("/errors/fnol:0000000000000000");

    await waitFor(() => expect(screen.getByText(/Entry not found/i)).toBeInTheDocument());
    expect(screen.getByText(/INFO\/DEBUG/i)).toBeInTheDocument();
  });

  it("renders a 503 banner when the route is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { detail: "error detail is unavailable — OPENAI_API_KEY is not configured" },
            503,
          ),
        ),
    );

    renderAt("/errors/fnol:aaaa111122223333");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /Error detail unavailable/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/OPENAI_API_KEY/)).toBeInTheDocument();
  });

  it("renders citations as links pointing at each cited entry", async () => {
    const body = detailBody({
      analysis: {
        answer: "Root cause likely upstream.",
        citations: [
          {
            id: "fnol:cccc111122223333",
            timestamp: "2026-06-05T09:55:00Z",
            level: "ERROR",
            app: "fnol",
            event: "sda_upstream_unreachable",
            raw: "raw",
            score: 0.92,
          },
        ],
        dry_run: false,
        tool_budget_exhausted: false,
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(body)));

    renderAt("/errors/fnol:aaaa111122223333");

    // Wait for the citations list — the link itself is the unambiguous signal.
    await waitFor(() => expect(screen.getAllByTestId("citation-link").length).toBe(1));
    const links = screen.getAllByTestId("citation-link");
    expect(links[0]).toHaveAttribute("href", "/errors/fnol%3Acccc111122223333");
    // No DRY RUN banner when dry_run=false.
    expect(screen.queryByText("DRY RUN")).toBeNull();
  });

  it("calls /api/errors/{id} once with the bearer token on mount", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(detailBody()));
    vi.stubGlobal("fetch", fetchSpy);

    renderAt("/errors/fnol:aaaa111122223333");

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/api/errors/fnol%3Aaaaa111122223333");
    expect((init as RequestInit).method).toBeUndefined(); // default GET
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.get("Authorization")).toBe("Bearer test-token");
  });
});
