import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../lib/auth-context";
import { AiChat } from "../pages/AiChat";
import type { ChatResponse } from "../types/chat";

interface SseEvent {
  event: string;
  data: unknown;
}

function encodeSse(events: SseEvent[]): string {
  return events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join("");
}

function sseResponse(events: SseEvent[]): Response {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(encodeSse(events)));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function chatComplete(over: Partial<ChatResponse> = {}): SseEvent {
  return {
    event: "complete",
    data: {
      answer: over.answer ?? "DRY_RUN: agent did not contact OpenAI.",
      citations: over.citations ?? [],
      session_id: over.session_id ?? "sess-1234",
      dry_run: over.dry_run ?? true,
      tool_budget_exhausted: over.tool_budget_exhausted ?? false,
    },
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

  it("submits the input via SSE and renders the agent's answer + dry-run banner", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(
        sseResponse([
          { event: "node", data: { node: "ingest", tool_budget_remaining: 4 } },
          chatComplete({ answer: "the answer", dry_run: true }),
        ]),
      );
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    const input = screen.getByLabelText(/Ask the agent/i);
    await userEvent.type(input, "why is fnol failing?");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByText("the answer")).toBeInTheDocument());
    expect(screen.getByText(/DRY RUN/i)).toBeInTheDocument();

    // The request body always carries streaming=true now.
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.streaming).toBe(true);
    expect(body.message).toBe("why is fnol failing?");
  });

  it("renders per-node status text while the stream is in progress", async () => {
    // Build a stream that yields one node event, then a final complete after a tick.
    // The handler reads the body in chunks — emit each chunk separately so the
    // node status renders BEFORE the complete event resolves the pending state.
    let pushChunk: ((chunk: string) => void) | undefined;
    let closeStream: (() => void) | undefined;
    const body = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        pushChunk = (chunk: string) => controller.enqueue(encoder.encode(chunk));
        closeStream = () => controller.close();
      },
    });
    const fetchSpy = vi.fn().mockResolvedValueOnce(
      new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "hi");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    // Emit a `correlate` node event → status becomes "Searching logs…".
    pushChunk?.(
      `event: node\ndata: ${JSON.stringify({ node: "correlate", tool_budget_remaining: 3 })}\n\n`,
    );

    await waitFor(() =>
      expect(screen.getByTestId("stream-status")).toHaveTextContent(/Searching logs/i),
    );

    // Finalise so the test cleans up properly.
    pushChunk?.(`event: complete\ndata: ${JSON.stringify(chatComplete().data)}\n\n`);
    closeStream?.();

    await waitFor(() => expect(screen.queryByTestId("stream-status")).not.toBeInTheDocument());
  });

  it("renders citation chips when the response carries citations", async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(
      sseResponse([
        chatComplete({
          citations: [
            {
              id: "fnol:aaaa111122223333",
              timestamp: "2026-06-05T10:00:00Z",
              level: "ERROR",
              app: "fnol",
              event: "request_failed",
              raw: "ERROR fnol request_failed",
              score: 0.12,
            },
          ],
        }),
      ]),
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
      .mockResolvedValueOnce(sseResponse([chatComplete({ session_id: "sess-A" })]))
      .mockResolvedValueOnce(
        sseResponse([chatComplete({ session_id: "sess-A", answer: "second" })]),
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

  it("shows the Thinking indicator with initial status while pending", async () => {
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

    await waitFor(() => expect(screen.getByTestId("thinking-indicator")).toBeInTheDocument());
    // Initial status copy is the `ingest` label until the first node event lands.
    expect(screen.getByTestId("stream-status")).toHaveTextContent(/Reading your question/i);
    expect(screen.getByRole("button", { name: /Thinking/i })).toBeDisabled();

    // Resolve the fetch so React's act doesn't complain about pending state.
    resolveFetch?.(sseResponse([chatComplete()]));
  });

  it("renders the tool-budget-exhausted badge when the agent reports it", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(sseResponse([chatComplete({ tool_budget_exhausted: true })]));
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "ask");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByText(/tool budget exhausted/i)).toBeInTheDocument());
  });

  it("does not show the dry-run banner until at least one turn returns dry_run=true", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(sseResponse([chatComplete({ dry_run: false, answer: "real" })]));
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    // Empty state: banner is absent.
    expect(screen.queryByTestId("dry-run-banner")).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "ask");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    await waitFor(() => expect(screen.getByText("real")).toBeInTheDocument());
    // dry_run=false answer landed → banner still absent.
    expect(screen.queryByTestId("dry-run-banner")).not.toBeInTheDocument();
  });

  it("shows the persistent dry-run banner once an answer returns dry_run=true", async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(sseResponse([chatComplete({ dry_run: true })]));
    vi.stubGlobal("fetch", fetchSpy);

    renderChat();
    await userEvent.type(screen.getByLabelText(/Ask the agent/i), "ask");
    await userEvent.click(screen.getByRole("button", { name: /Send/i }));

    const banner = await screen.findByTestId("dry-run-banner");
    expect(banner).toHaveTextContent(/Dry-run mode/i);
    expect(banner).toHaveTextContent(/DASHBOARD_LLM_DRY_RUN=false/);
    expect(banner).toHaveTextContent(/restart/i);
    expect(banner).toHaveTextContent(/ADR-015/);
  });

  it("surfaces an HTTP error when the pre-flight request fails with 5xx", async () => {
    // Pre-flight failures arrive as a JSON Response (not an SSE stream) so the
    // client never reads from response.body.getReader().
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
