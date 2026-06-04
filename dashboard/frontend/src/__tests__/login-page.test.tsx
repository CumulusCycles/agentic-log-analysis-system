import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { LoginPage } from "../pages/LoginPage";

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <LoginPage />
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
  it("renders the username + password fields and submit button", () => {
    renderLogin();
    expect(
      screen.getByRole("textbox", { name: /username/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign in/i }),
    ).toBeInTheDocument();
  });

  it("stores the token returned by the API after a successful submit", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "tok-1",
          token_type: "bearer",
          expires_in: 3600,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderLogin();
    await userEvent.type(
      screen.getByRole("textbox", { name: /username/i }),
      "admin",
    );
    await userEvent.type(screen.getByLabelText(/password/i), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(localStorage.getItem("dashboard_token")).toBe("tok-1"),
    );
    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url] = fetchSpy.mock.calls[0];
    expect(url).toMatch(/\/api\/auth\/login$/);
  });

  it("shows the API error detail when login fails", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid credentials" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderLogin();
    await userEvent.type(
      screen.getByRole("textbox", { name: /username/i }),
      "admin",
    );
    await userEvent.type(screen.getByLabelText(/password/i), "WRONG");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "invalid credentials",
    );
    expect(localStorage.getItem("dashboard_token")).toBeNull();
  });
});
