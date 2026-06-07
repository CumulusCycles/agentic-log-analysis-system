import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "../components/Sparkline";
import type { StatusHistoryBucket } from "../types/logs";

const BUCKETS: StatusHistoryBucket[] = [
  { ts: "2026-06-07T00:00:00Z", info: 5, warn: 1, error: 0 },
  { ts: "2026-06-07T01:00:00Z", info: 3, warn: 0, error: 0 },
  { ts: "2026-06-07T02:00:00Z", info: 10, warn: 2, error: 1 },
  { ts: "2026-06-07T03:00:00Z", info: 7, warn: 0, error: 0 },
];

describe("Sparkline", () => {
  it("renders a sparkline container with the expected fixed height", () => {
    render(<Sparkline buckets={BUCKETS} />);
    const el = screen.getByTestId("sparkline");
    expect(el).toBeInTheDocument();
    expect(el.style.height).toBe("56px");
  });

  it("is marked aria-hidden so screen readers ignore decorative chart", () => {
    render(<Sparkline buckets={BUCKETS} />);
    expect(screen.getByTestId("sparkline").getAttribute("aria-hidden")).toBe("true");
  });

  it("renders without crashing when given an empty bucket array", () => {
    render(<Sparkline buckets={[]} />);
    expect(screen.getByTestId("sparkline")).toBeInTheDocument();
  });
});
