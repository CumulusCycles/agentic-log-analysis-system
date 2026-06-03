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
      user_id: "agent-1-uuid",
      role: "agent",
      app: "agent-portal",
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
  localStorage.setItem("agent_portal_token", makeTestToken());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProfilePage", () => {
  it("renders the agent profile fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "agent-1-uuid",
            username: "agent1",
            role: "agent",
            display_name: "Agent One",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    renderProfile();
    await waitFor(() =>
      expect(screen.getByText("Agent One")).toBeInTheDocument(),
    );
    expect(screen.getByText("agent1")).toBeInTheDocument();
    expect(screen.getByText("agent")).toBeInTheDocument();
  });
});
