import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "../hooks/use-polling";

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("runs fn on mount and again on every interval tick", () => {
    const fn = vi.fn();
    renderHook(() => usePolling(fn, 1_000));

    expect(fn).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1_000);
    expect(fn).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(2_000);
    expect(fn).toHaveBeenCalledTimes(4);
  });

  it("clears the interval on unmount", () => {
    const fn = vi.fn();
    const { unmount } = renderHook(() => usePolling(fn, 1_000));

    expect(fn).toHaveBeenCalledTimes(1);
    unmount();

    vi.advanceTimersByTime(5_000);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
