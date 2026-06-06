import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ProactiveFindingsPanel } from "../components/ProactiveFindingsPanel";
import type { ProactiveFinding } from "../types/proactive";

function makeFinding(overrides: Partial<ProactiveFinding> = {}): ProactiveFinding {
  return {
    id: "proactive:f1",
    scan_started_at: "2026-06-06T12:00:00Z",
    scan_completed_at: "2026-06-06T12:00:01Z",
    summary: "WARN cluster in fnol over last 10 minutes.",
    severity: "warn",
    citations: [
      {
        id: "fnol:abcdef0123456789",
        timestamp: "2026-06-06T11:59:55Z",
        level: "WARN",
        app: "fnol",
        event: "chaos_honored",
        raw: "directive=slow:500 status=200",
        score: 0.7,
      },
    ],
    dry_run: false,
    ...overrides,
  };
}

function renderPanel(props: {
  findings?: ProactiveFinding[];
  scanEnabled?: boolean;
  lastScanAt?: string | null;
}) {
  return render(
    <MemoryRouter>
      <ProactiveFindingsPanel
        findings={props.findings ?? []}
        scanEnabled={props.scanEnabled ?? false}
        lastScanAt={props.lastScanAt ?? null}
      />
    </MemoryRouter>,
  );
}

describe("ProactiveFindingsPanel", () => {
  it("renders nothing when scan disabled AND no findings", () => {
    const { container } = renderPanel({ scanEnabled: false, findings: [] });
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the empty-state copy when scan enabled but no findings yet", () => {
    renderPanel({ scanEnabled: true, findings: [], lastScanAt: "2026-06-06T12:00:00Z" });
    expect(screen.getByTestId("proactive-findings-panel")).toBeInTheDocument();
    expect(screen.getByTestId("proactive-findings-empty")).toHaveTextContent(/no anomalies/i);
    expect(screen.getByTestId("last-scan-at")).toBeInTheDocument();
  });

  it("renders findings newest-first when caller has already sorted them", () => {
    const findings = [
      makeFinding({ id: "proactive:newest", summary: "newest summary" }),
      makeFinding({ id: "proactive:older", summary: "older summary" }),
    ];
    renderPanel({ scanEnabled: true, findings });
    const items = screen.getAllByTestId("proactive-finding");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent(/newest summary/);
    expect(items[1]).toHaveTextContent(/older summary/);
  });

  it("colors the severity pill consistently per severity", () => {
    const findings = [
      makeFinding({ id: "proactive:err", severity: "error" }),
      makeFinding({ id: "proactive:warn", severity: "warn" }),
      makeFinding({ id: "proactive:info", severity: "info" }),
    ];
    renderPanel({ scanEnabled: true, findings });
    const pills = screen.getAllByTestId("severity-pill");
    expect(pills[0]).toHaveTextContent(/error/i);
    expect(pills[0].className).toContain("bg-red");
    expect(pills[1]).toHaveTextContent(/warn/i);
    expect(pills[1].className).toContain("bg-amber");
    expect(pills[2]).toHaveTextContent(/info/i);
    expect(pills[2].className).toContain("bg-slate");
  });

  it("renders citation links pointing at /errors/:id", () => {
    const finding = makeFinding();
    renderPanel({ scanEnabled: true, findings: [finding] });
    const link = screen.getByTestId("proactive-citation-link");
    expect(link).toHaveAttribute("href", "/errors/fnol:abcdef0123456789");
    expect(link).toHaveTextContent(/fnol.*chaos_honored/);
  });

  it("marks dry-run findings explicitly", () => {
    const finding = makeFinding({ dry_run: true });
    renderPanel({ scanEnabled: true, findings: [finding] });
    expect(screen.getByText(/dry-run/)).toBeInTheDocument();
  });
});
