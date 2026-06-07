import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { postChatStream } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Citation } from "../types/chat";

interface ChatTurn {
  user: string;
  assistant: string;
  citations: Citation[];
  dryRun: boolean;
  toolBudgetExhausted: boolean;
}

// Per-node copy shown above the answer while the agent is mid-stream.
// Keyed on the node names emitted by the backend `_stream_chat_events`
// SSE generator (see routers/chat.py).
const NODE_STATUS_COPY: Record<string, string> = {
  ingest: "Reading your question…",
  analyze: "Analysing…",
  correlate: "Searching logs…",
  predict: "Synthesising…",
  respond: "Drafting answer…",
};

export function AiChat() {
  const { token, logout } = useAuth();
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Cancel any in-flight stream on unmount so the fetch reader doesn't
  // keep a dangling reference after navigation.
  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  // Scroll to the newest turn after every history update. Guard for
  // jsdom (Vitest), which doesn't implement Element.scrollIntoView.
  useEffect(() => {
    const target = bottomRef.current;
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [history, pending, streamStatus]);

  const submit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || !token || pending) return;

      // Abort any in-flight stream at the call site rather than relying on
      // an effect cleanup. In React 18 StrictMode the mount-only cleanup
      // can race with a submit() that's already begun; aborting here
      // guarantees a clean handoff.
      controllerRef.current?.abort();

      setError(null);
      setPending(true);
      setStreamStatus(NODE_STATUS_COPY.ingest);

      controllerRef.current = postChatStream(
        token,
        { message: trimmed, session_id: sessionId ?? undefined },
        {
          onNode: (ev) => {
            const label = NODE_STATUS_COPY[ev.node];
            if (label) setStreamStatus(label);
          },
          onComplete: (ev) => {
            setSessionId(ev.session_id);
            setHistory((prev) => [
              ...prev,
              {
                user: trimmed,
                assistant: ev.answer,
                citations: ev.citations,
                dryRun: ev.dry_run,
                toolBudgetExhausted: ev.tool_budget_exhausted,
              },
            ]);
            setInput("");
            setStreamStatus(null);
            setPending(false);
            controllerRef.current = null;
          },
          onError: (detail, status) => {
            if (status === 401) {
              logout();
              return;
            }
            setError(status > 0 ? `${status}: ${detail}` : detail);
            setStreamStatus(null);
            setPending(false);
            controllerRef.current = null;
          },
        },
      );
    },
    [input, token, pending, sessionId, logout],
  );

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">AI Chat</h1>
          <p className="text-sm text-slate-500">
            Ask about errors, status, anything across the four apps. The agent searches the log
            corpus and returns cited entries.
          </p>
        </div>
        {sessionId && (
          <span
            className="rounded-md bg-slate-100 px-2 py-1 text-xs font-mono text-slate-600"
            title={`session ${sessionId}`}
          >
            session: {sessionId.slice(0, 8)}…
          </span>
        )}
      </header>

      <div
        className="flex min-h-[400px] flex-col gap-4 rounded-lg border border-slate-200 bg-white p-4"
        role="log"
        aria-live="polite"
        aria-label="conversation"
      >
        {history.length === 0 && !pending && (
          <p className="text-sm text-slate-400">
            No messages yet. Try: <span className="font-mono">why is FNOL failing?</span>
          </p>
        )}
        {history.map((turn, i) => (
          <ChatTurnView key={i} turn={turn} />
        ))}
        {pending && <ThinkingIndicator status={streamStatus} />}
        <div ref={bottomRef} />
      </div>

      {history.some((t) => t.dryRun) && <DryRunBanner />}

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      <form onSubmit={submit} className="flex items-end gap-2">
        <label htmlFor="chat-input" className="sr-only">
          Ask the agent
        </label>
        <textarea
          id="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
          maxLength={4000}
          disabled={pending}
          placeholder="ask the agent…"
          className="min-h-[60px] flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={pending || !input.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {pending ? "Thinking…" : "Send"}
        </button>
      </form>
    </div>
  );
}

function DryRunBanner() {
  return (
    <div
      role="status"
      data-testid="dry-run-banner"
      className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
    >
      <strong>Dry-run mode.</strong> Answers are canned (no OpenAI calls, no spend). To enable real
      LLM responses, set <code className="rounded bg-white px-1">DASHBOARD_LLM_DRY_RUN=false</code>{" "}
      in <code className="rounded bg-white px-1">.env</code> and restart{" "}
      <code className="rounded bg-white px-1">log-dashboard</code>. See ADR-015 for the
      safe-by-default rationale.
    </div>
  );
}

function ChatTurnView({ turn }: { turn: ChatTurn }) {
  return (
    <div className="flex flex-col gap-3 border-b border-slate-100 pb-3 last:border-b-0">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">You</span>
        <p className="whitespace-pre-wrap text-sm text-slate-900">{turn.user}</p>
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Agent
          </span>
          {turn.dryRun && (
            <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              DRY RUN
            </span>
          )}
          {turn.toolBudgetExhausted && (
            <span className="rounded-md bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800">
              tool budget exhausted
            </span>
          )}
        </div>
        <p className="whitespace-pre-wrap text-sm text-slate-900">{turn.assistant}</p>
        {turn.citations.length > 0 && <CitationsRow citations={turn.citations} />}
      </div>
    </div>
  );
}

function CitationsRow({ citations }: { citations: Citation[] }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-slate-500">Citations ({citations.length})</span>
      <div className="flex flex-wrap gap-1">
        {citations.map((c) => (
          <Link
            key={c.id}
            to={`/logs?app=${encodeURIComponent(c.app)}`}
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-100"
            title={c.raw}
          >
            <span className="font-mono text-slate-500">{c.app}</span>
            <span className="font-semibold">{c.level}</span>
            <span>{c.event}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function ThinkingIndicator({ status }: { status: string | null }) {
  return (
    <div
      className="flex items-center gap-2"
      aria-label="agent is thinking"
      data-testid="thinking-indicator"
    >
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Agent</span>
      {status && (
        <span className="text-xs text-slate-600" data-testid="stream-status">
          {status}
        </span>
      )}
      <span className="thinking-dots" aria-hidden="true">
        <span>.</span>
        <span>.</span>
        <span>.</span>
      </span>
      <style>{`
        .thinking-dots span {
          display: inline-block;
          animation: thinking-bounce 1.2s infinite ease-in-out;
          opacity: 0.4;
        }
        .thinking-dots span:nth-child(1) { animation-delay: 0s; }
        .thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
        .thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes thinking-bounce {
          0%, 80%, 100% { opacity: 0.3; }
          40% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
