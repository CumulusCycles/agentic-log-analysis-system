import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { LogExplorer } from "../pages/LogExplorer";
import type { LogEntry, LogsResponse } from "../types/logs";

function entry(over: Partial<LogEntry> = {}): LogEntry {
  return {
    id: over.id ?? "fnol:1",
    timestamp: over.timestamp ?? "2026-06-04T16:30:00Z",
    level: over.level ?? "INFO",
    app: over.app ?? "fnol",
    event: over.event ?? "request",
    fields: over.fields ?? {},
    raw: over.raw ?? "raw line",
  };
}

function response(
  entries: LogEntry[],
  nextBefore: string | null = null,
): LogsResponse {
  return { entries, next_before: nextBefore };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function renderExplorer(initialEntry = "/logs") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
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

describe("LogExplorer", () => {
  it("refetches with a narrower app filter when an app checkbox is toggled off", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(response([])));
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());

    // Initial fetch has all 4 apps in the query.
    const initialUrl = String(fetchSpy.mock.calls[0][0]);
    expect(initialUrl).toMatch(
      /app=shared-data-api%2Cfnol%2Ccustomer-portal%2Cagent-portal/,
    );

    fetchSpy.mockClear();

    // Toggle FNOL off.
    await userEvent.click(screen.getByTestId("filter-app-fnol"));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const filteredUrl = String(fetchSpy.mock.calls[0][0]);
    expect(filteredUrl).not.toMatch(/fnol/);
    expect(filteredUrl).toMatch(/shared-data-api/);
  });

  it("sends a before= cursor when Load more is clicked", async () => {
    const page1 = response([entry({ id: "fnol:1" })], "2026-06-04T16:00:00Z");
    const page2 = response([entry({ id: "fnol:2" })]);
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(page1))
      .mockResolvedValueOnce(jsonResponse(page2));
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer();

    await waitFor(() =>
      expect(screen.getByTestId("load-more")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByTestId("load-more"));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    const secondUrl = String(fetchSpy.mock.calls[1][0]);
    expect(secondUrl).toMatch(/before=2026-06-04T16%3A00%3A00Z/);
  });

  it("pre-selects only the FNOL filter when arriving with ?app=fnol", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(response([])));
    vi.stubGlobal("fetch", fetchSpy);

    renderExplorer("/logs?app=fnol");

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toMatch(/app=fnol(&|$)/);
    expect(url).not.toMatch(/customer-portal/);
  });
});
