import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { ProfilePage } from "../pages/ProfilePage";

function makeTestToken(): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({
      iss: "shared-data-api",
      aud: "agentic-log-analysis-insurance-apps",
      user_id: "u-1",
      role: "customer",
      app: "customer-portal",
      iat: 0,
      exp: 9999999999,
    }),
  );
  return `${header}.${payload}.sig`;
}

function renderProfile() {
  return render(
    <MemoryRouter initialEntries={["/profile"]}>
      <AuthProvider>
        <ProfilePage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("customer_portal_token", makeTestToken());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProfilePage", () => {
  it("renders the customer profile fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "u-1",
            username: "alice",
            role: "customer",
            display_name: "Alice Anderson",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderProfile();
    await waitFor(() =>
      expect(screen.getByText("Alice Anderson")).toBeInTheDocument(),
    );
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("customer")).toBeInTheDocument();
  });
});
