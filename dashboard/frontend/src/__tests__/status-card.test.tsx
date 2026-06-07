import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { StatusCard } from "../components/StatusCard";
import type { AppStatus, StatusHistoryBucket } from "../types/logs";

const SAMPLE: AppStatus = {
  name: "shared-data-api",
  status: "ok",
  file_present: true,
  last_seen_at: "2026-06-04T16:30:00Z",
  counts_1h: { info: 100, warn: 2, error: 0 },
  counts_24h: { info: 1500, warn: 30, error: 1 },
  counts_7d: { info: 12000, warn: 200, error: 5 },
};

function renderCard(status: AppStatus, history?: StatusHistoryBucket[]) {
  return render(
    <MemoryRouter>
      <StatusCard status={status} history={history} />
    </MemoryRouter>,
  );
}

describe("StatusCard", () => {
  it("renders the app name and the 1h/24h/7d counts", () => {
    renderCard(SAMPLE);
    expect(screen.getByText("shared-data-api")).toBeInTheDocument();
    expect(screen.getByText("1 hour")).toBeInTheDocument();
    expect(screen.getByText("24 hours")).toBeInTheDocument();
    expect(screen.getByText("7 days")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("12000")).toBeInTheDocument();
  });

  it("links to the log explorer pre-filtered to this app", () => {
    renderCard(SAMPLE);
    const link = screen.getByTestId("status-card");
    expect(link.getAttribute("href")).toBe("/logs?app=shared-data-api");
  });

  it("does not render a sparkline when history is undefined", () => {
    renderCard(SAMPLE);
    expect(screen.queryByTestId("status-card-sparkline")).not.toBeInTheDocument();
  });

  it("does not render a sparkline when history is an empty array", () => {
    renderCard(SAMPLE, []);
    expect(screen.queryByTestId("status-card-sparkline")).not.toBeInTheDocument();
  });

  it("renders a sparkline when history has buckets", () => {
    renderCard(SAMPLE, [
      { ts: "2026-06-07T00:00:00Z", info: 5, warn: 0, error: 0 },
      { ts: "2026-06-07T01:00:00Z", info: 10, warn: 1, error: 0 },
    ]);
    expect(screen.getByTestId("status-card-sparkline")).toBeInTheDocument();
  });
});
