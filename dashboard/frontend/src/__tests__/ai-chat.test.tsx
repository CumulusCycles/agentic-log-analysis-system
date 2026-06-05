import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { AiChat } from "../pages/AiChat";
import type { ChatResponse } from "../types/chat";

function chatResponse(over: Partial<ChatResponse> = {}): ChatResponse {
  return {
    answer: over.answer ?? "DRY_RUN: agent did not contact OpenAI.",
    citations: over.citations ?? [],
    session_id: over.session_id ?? "sess-1234",
    dry_run: over.dry_run ?? true,
    tool_budget_exhausted: over.tool_budget_exhausted ?? false,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderChat() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <AiChat />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("dashboard_token", "test-token");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AiChat", () => {
  it("renders the empty state when no messages yet", () => {
    renderChat();
    expect(screen.getByRole("heading", { name: /AI Chat/i })).toBeInTheDocument();
    expect(screen.getByText(/No messages yet/i)).toBeInTheDocument();
  });

  it("submits the input and renders the agent's answer + dry-run banner", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(chatResponse({ answer: "the answer", dry_run: true })));
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    const input = screen.getByLabelText(/Ask the agent/i);
    await userEvent.type(input, "why is fnol failing?");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByText("the answer")).toBeInTheDocument());
    expect(screen.getByText(/DRY RUN/i)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/chat"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ message: "why is fnol failing?" }),
      }),
    );
  });

  it("renders citation chips when the response carries citations", async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(
      jsonResponse(
        chatResponse({
          citations: [
            {
              id: "fnol:1",
              timestamp: "2026-06-05T10:00:00Z",
              level: "ERROR",
              app: "fnol",
              event: "request_failed",
              raw: "ERROR fnol request_failed",
              score: 0.12,
            },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "hello");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByText(/Citations \(1\)/i)).toBeInTheDocument());
    expect(screen.getByText("request_failed")).toBeInTheDocument();
    expect(screen.getByText("ERROR")).toBeInTheDocument();
  });

  it("echoes the same session_id on follow-up turns", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(chatResponse({ session_id: "sess-A" })))
      .mockResolvedValueOnce(
        jsonResponse(chatResponse({ session_id: "sess-A", answer: "second" })),
      );
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    const input = screen.getByLabelText(/Ask the agent/i);
    await userEvent.type(input, "first");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));
    await waitFor(() => expect(screen.getByText(/sess-A/)).toBeInTheDocument());

    await userEvent.type(input, "second question");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByText("second")).toBeInTheDocument());
    const secondCall = fetchSpy.mock.calls[1];
    const body = JSON.parse((secondCall[1] as RequestInit).body as string);
    expect(body.session_id).toBe("sess-A");
  });

  it("shows a Thinking indicator while pending", async () => {
    // Hold the fetch open so the button stays in pending state during assertion.
    let resolveFetch: ((value: Response) => void) | undefined;
    const fetchSpy = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "hello");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByLabelText(/agent is thinking/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Thinking/i })).toBeDisabled();

    // Resolve the fetch so React's act doesn't complain about pending state.
    resolveFetch?.(jsonResponse(chatResponse()));
  });

  it("renders the tool-budget-exhausted badge when the agent reports it", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(chatResponse({ tool_budget_exhausted: true })));
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "ask");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByText(/tool budget exhausted/i)).toBeInTheDocument());
  });

  it("surfaces an HTTP error when the request fails with 5xx", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "upstream LLM unavailable" }, 502));
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "ask");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent(/502/);
  });
});
