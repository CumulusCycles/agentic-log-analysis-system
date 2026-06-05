import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { LoginPage } from "../pages/LoginPage";

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/claims" element={<div>claims-landing</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LoginPage", () => {
  it("renders username + password fields and the submit button", () => {
    renderLogin();
    expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("stores the token returned by the API after a successful submit", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "tok-1",
          token_type: "bearer",
          expires_in: 60,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderLogin();
    await userEvent.type(screen.getByRole("textbox", { name: /username/i }), "agent1");
    await userEvent.type(screen.getByLabelText(/password/i), "agent");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(localStorage.getItem("agent_portal_token")).toBe("tok-1"));
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

  it("shows the upstream error detail when login fails", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid credentials" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderLogin();
    await userEvent.type(screen.getByRole("textbox", { name: /username/i }), "agent1");
    await userEvent.type(screen.getByLabelText(/password/i), "WRONG");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid credentials");
    expect(localStorage.getItem("agent_portal_token")).toBeNull();
  });
});
