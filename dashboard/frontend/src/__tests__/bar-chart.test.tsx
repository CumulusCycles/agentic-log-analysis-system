import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BarChart } from "../components/BarChart";

describe("BarChart", () => {
  it("renders one row per datum with label + count", () => {
    render(
      <BarChart
        data={[
          { label: "fnol", value: 200 },
          { label: "shared-data-api", value: 170 },
        ]}
      />,
    );
    expect(screen.getByText("fnol")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("shared-data-api")).toBeInTheDocument();
    expect(screen.getByText("170")).toBeInTheDocument();
    expect(screen.getAllByTestId("bar-chart-bar")).toHaveLength(2);
  });

  it("computes the widest bar at 100% relative to the max value", () => {
    render(
      <BarChart
        data={[
          { label: "a", value: 100 },
          { label: "b", value: 50 },
        ]}
      />,
    );
    const bars = screen.getAllByTestId("bar-chart-bar");
    // The first bar (max) should be 100% wide.
    expect((bars[0] as HTMLElement).style.width).toBe("100%");
    // The second bar should be ~50% wide.
    expect((bars[1] as HTMLElement).style.width).toBe("50%");
  });

  it("renders 0-value bars with 0% width without throwing NaN", () => {
    render(
      <BarChart
        data={[
          { label: "z", value: 0 },
          { label: "a", value: 5 },
        ]}
      />,
    );
    const bars = screen.getAllByTestId("bar-chart-bar");
    // Zero-value row: 0% width.
    expect((bars[0] as HTMLElement).style.width).toBe("0%");
    // Non-zero row: 100% width (it's the max).
    expect((bars[1] as HTMLElement).style.width).toBe("100%");
  });

  it("renders the emptyHint when data is empty", () => {
    render(<BarChart data={[]} emptyHint="no rows here" />);
    expect(screen.getByText("no rows here")).toBeInTheDocument();
    expect(screen.queryByTestId("bar-chart")).not.toBeInTheDocument();
  });
});
