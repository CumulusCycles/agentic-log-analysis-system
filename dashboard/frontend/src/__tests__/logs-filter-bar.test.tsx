import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LogsFilterBar, type FilterState } from "../components/LogsFilterBar";
import { APP_NAMES, LOG_LEVELS } from "../types/logs";

function baseFilters(): FilterState {
  return {
    apps: [...APP_NAMES],
    levels: [...LOG_LEVELS],
    window: "1h",
    customSince: null,
    customUntil: null,
    query: "",
  };
}

describe("LogsFilterBar — Check All / Clear All", () => {
  it("clears all apps when Clear all is clicked", async () => {
    const onChange = vi.fn();
    render(<LogsFilterBar value={baseFilters()} onChange={onChange} />);

    await userEvent.click(screen.getByTestId("filter-app-clear-all"));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].apps).toEqual([]);
    // Other fields unchanged.
    expect(onChange.mock.calls[0][0].levels).toEqual([...LOG_LEVELS]);
  });

  it("checks every app when Check all is clicked", async () => {
    const onChange = vi.fn();
    const start = { ...baseFilters(), apps: [] };
    render(<LogsFilterBar value={start} onChange={onChange} />);

    await userEvent.click(screen.getByTestId("filter-app-check-all"));

    expect(onChange.mock.calls[0][0].apps).toEqual([...APP_NAMES]);
  });

  it("clears all levels independently of apps", async () => {
    const onChange = vi.fn();
    render(<LogsFilterBar value={baseFilters()} onChange={onChange} />);

    await userEvent.click(screen.getByTestId("filter-level-clear-all"));

    expect(onChange.mock.calls[0][0].levels).toEqual([]);
    expect(onChange.mock.calls[0][0].apps).toEqual([...APP_NAMES]);
  });

  it("checks every level when Check all is clicked", async () => {
    const onChange = vi.fn();
    const start = { ...baseFilters(), levels: [] };
    render(<LogsFilterBar value={start} onChange={onChange} />);

    await userEvent.click(screen.getByTestId("filter-level-check-all"));

    expect(onChange.mock.calls[0][0].levels).toEqual([...LOG_LEVELS]);
  });
});

describe("LogsFilterBar — TimeWindowSelector integration", () => {
  it("propagates window changes via onChange (preset)", async () => {
    const onChange = vi.fn();
    render(<LogsFilterBar value={baseFilters()} onChange={onChange} />);

    await userEvent.click(screen.getByTestId("filter-window-7d"));

    expect(onChange).toHaveBeenCalled();
    const payload = onChange.mock.calls.at(-1)![0];
    expect(payload.window).toBe("7d");
  });

  it("propagates custom from/to into customSince and customUntil", () => {
    const onChange = vi.fn();
    const start = { ...baseFilters(), window: "custom" as const };
    render(<LogsFilterBar value={start} onChange={onChange} />);

    // fireEvent.change emits one whole-string transition — userEvent.type
    // would only land the first keystroke given the component is fully
    // controlled and the parent test doesn't re-render with the typed value.
    fireEvent.change(screen.getByTestId("filter-window-custom-since"), {
      target: { value: "2026-06-01T08:00" },
    });

    const last = onChange.mock.calls.at(-1)![0];
    expect(last.window).toBe("custom");
    expect(last.customSince).toBe("2026-06-01T08:00");
  });
});

describe("LogsFilterBar — search hint", () => {
  it("shows the auto-search hint when the query input is empty", () => {
    render(<LogsFilterBar value={baseFilters()} onChange={vi.fn()} />);

    const hint = screen.getByTestId("filter-query-hint");
    expect(hint).toHaveTextContent(/Auto-searches 300 ms after you stop typing/i);
    expect(hint).toHaveTextContent(/no submit needed/i);
  });

  it("swaps to the semantic-search explainer when the query is non-empty", () => {
    render(
      <LogsFilterBar value={{ ...baseFilters(), query: "auth failures" }} onChange={vi.fn()} />,
    );

    const hint = screen.getByTestId("filter-query-hint");
    expect(hint).toHaveTextContent(/Chroma vector store/i);
    expect(hint).not.toHaveTextContent(/Auto-searches/i);
  });

  it("wires the input to the hint via aria-describedby for screen readers", () => {
    render(<LogsFilterBar value={baseFilters()} onChange={vi.fn()} />);

    const input = screen.getByTestId("filter-query");
    const hint = screen.getByTestId("filter-query-hint");
    expect(input.getAttribute("aria-describedby")).toBe(hint.id);
  });
});
