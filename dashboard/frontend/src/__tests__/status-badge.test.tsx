import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "../components/StatusBadge";

describe("StatusBadge", () => {
  it("renders ok with the emerald palette", () => {
    render(<StatusBadge status="ok" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("ok");
    expect(badge.className).toMatch(/emerald/);
  });

  it("renders degraded with the amber palette", () => {
    render(<StatusBadge status="degraded" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("degraded");
    expect(badge.className).toMatch(/amber/);
  });

  it("renders error with the red palette", () => {
    render(<StatusBadge status="error" />);
    const badge = screen.getByTestId("status-badge");
    expect(badge).toHaveTextContent("error");
    expect(badge.className).toMatch(/red/);
  });
});
