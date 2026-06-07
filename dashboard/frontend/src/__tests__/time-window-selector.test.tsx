import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TimeWindowSelector } from "../components/TimeWindowSelector";
import {
  resolveTimeWindow,
  type TimeWindowChange,
  type TimeWindowPreset,
} from "../lib/time-window";

function renderSelector(
  initial: {
    value?: TimeWindowPreset;
    customSince?: string | null;
    customUntil?: string | null;
  } = {},
) {
  const onChange = vi.fn<(next: TimeWindowChange) => void>();
  render(
    <TimeWindowSelector
      value={initial.value ?? "1h"}
      customSince={initial.customSince ?? null}
      customUntil={initial.customUntil ?? null}
      onChange={onChange}
    />,
  );
  return { onChange };
}

describe("TimeWindowSelector", () => {
  it("renders four presets", () => {
    renderSelector();
    expect(screen.getByTestId("time-window-1h")).toBeInTheDocument();
    expect(screen.getByTestId("time-window-24h")).toBeInTheDocument();
    expect(screen.getByTestId("time-window-7d")).toBeInTheDocument();
    expect(screen.getByTestId("time-window-custom")).toBeInTheDocument();
  });

  it("hides datetime-local fields when the preset is not custom", () => {
    renderSelector({ value: "24h" });
    expect(screen.queryByTestId("time-window-custom-since")).toBeNull();
    expect(screen.queryByTestId("time-window-custom-until")).toBeNull();
  });

  it("reveals datetime-local fields when Custom is selected", async () => {
    renderSelector({ value: "custom" });
    expect(screen.getByTestId("time-window-custom-since")).toBeInTheDocument();
    expect(screen.getByTestId("time-window-custom-until")).toBeInTheDocument();
  });

  it("emits a resolved since (and null until) when 24h is picked", async () => {
    const { onChange } = renderSelector({ value: "1h" });
    await userEvent.click(screen.getByTestId("time-window-24h"));

    expect(onChange).toHaveBeenCalledTimes(1);
    const payload = onChange.mock.calls[0][0];
    expect(payload.preset).toBe("24h");
    expect(payload.since).not.toBeNull();
    expect(payload.until).toBeNull();
    // since is roughly 24h ago — must parse and be within a generous window.
    const sinceMs = new Date(payload.since!).getTime();
    const expectedMs = Date.now() - 24 * 60 * 60 * 1000;
    expect(Math.abs(sinceMs - expectedMs)).toBeLessThan(5_000);
  });

  it("emits the operator's bounds (ISO Z) when a Custom field is set", () => {
    // Use fireEvent.change so the whole-string transition emits one onChange
    // payload — userEvent.type drives one keystroke at a time, but the
    // component is fully controlled and the test parent doesn't re-render
    // with the typed value, so only the first keystroke's payload would be
    // observable.
    const { onChange } = renderSelector({ value: "custom", customUntil: "2026-06-02T08:00" });

    fireEvent.change(screen.getByTestId("time-window-custom-since"), {
      target: { value: "2026-06-01T08:00" },
    });

    const last = onChange.mock.calls.at(-1)![0];
    expect(last.preset).toBe("custom");
    expect(last.customSince).toBe("2026-06-01T08:00");
    expect(last.customUntil).toBe("2026-06-02T08:00");
    // Resolved ISO strings include a TZ offset / Z suffix.
    expect(last.since).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(last.until).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    // Lower bound is strictly before the upper bound.
    expect(new Date(last.since!).getTime()).toBeLessThan(new Date(last.until!).getTime());
  });

  it("shows a hint when Custom is selected but one bound is missing", () => {
    renderSelector({ value: "custom", customSince: "2026-06-01T08:00", customUntil: null });
    expect(screen.getByText(/Pick both From and To/)).toBeInTheDocument();
  });
});

describe("resolveTimeWindow", () => {
  it("returns null until for preset windows", () => {
    const { since, until } = resolveTimeWindow("7d", null, null);
    expect(since).not.toBeNull();
    expect(until).toBeNull();
  });

  it("returns operator bounds for the custom preset", () => {
    const { since, until } = resolveTimeWindow("custom", "2026-06-01T08:00", "2026-06-02T08:00");
    expect(since).toMatch(/^2026-06-01T/);
    expect(until).toMatch(/^2026-06-02T/);
  });

  it("returns null bounds when custom is selected without inputs", () => {
    expect(resolveTimeWindow("custom", null, null)).toEqual({ since: null, until: null });
  });
});
