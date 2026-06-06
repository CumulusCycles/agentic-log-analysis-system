// Lightweight fetch wrapper. Production: relative paths (same origin as the
// FastAPI host). Dev: VITE_DASHBOARD_API_BASE_URL points at http://localhost:4001.

import type {
  AgitatorEnv,
  RunCreateRequest,
  RunListResponse,
  RunRecord,
  ScenarioSpec,
} from "../types/agitator";
import type { AdminOut, ApiError, LoginRequest, TokenResponse } from "../types/api";
import type { ChatRequest, ChatResponse } from "../types/chat";
import type { ErrorDetailResponse } from "../types/errors";
import type {
  LogsFilters,
  LogsResponse,
  LogsSearchRequest,
  LogsSearchResponse,
  StatusResponse,
} from "../types/logs";
import type { ChromaStatsResponse } from "../types/vectorstore";

const BASE_URL = import.meta.env.VITE_DASHBOARD_API_BASE_URL ?? "";

export class HttpError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "HttpError";
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = `request failed (${response.status})`;
    try {
      const body = (await response.json()) as ApiError;
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON body */
    }
    throw new HttpError(response.status, detail);
  }
  return (await response.json()) as T;
}

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getMe(token: string): Promise<AdminOut> {
  return request<AdminOut>("/api/auth/me", {}, token);
}

export async function getStatus(token: string): Promise<StatusResponse> {
  return request<StatusResponse>("/api/status", {}, token);
}

function buildLogsQuery(filters: LogsFilters): string {
  const params = new URLSearchParams();
  if (filters.apps.length > 0) params.set("app", filters.apps.join(","));
  if (filters.levels.length > 0) params.set("level", filters.levels.join(","));
  if (filters.since) params.set("since", filters.since);
  if (filters.before) params.set("before", filters.before);
  params.set("limit", String(filters.limit));
  return params.toString();
}

export async function getLogs(token: string, filters: LogsFilters): Promise<LogsResponse> {
  const qs = buildLogsQuery(filters);
  return request<LogsResponse>(`/api/logs?${qs}`, {}, token);
}

export async function searchLogs(
  token: string,
  body: LogsSearchRequest,
): Promise<LogsSearchResponse> {
  return request<LogsSearchResponse>(
    "/api/logs/search",
    { method: "POST", body: JSON.stringify(body) },
    token,
  );
}

// --- PR 3: Agitator ---

export async function listScenarios(token: string): Promise<ScenarioSpec[]> {
  return request<ScenarioSpec[]>("/api/agitator/scenarios", {}, token);
}

export async function getAgitatorEnv(token: string): Promise<AgitatorEnv> {
  return request<AgitatorEnv>("/api/agitator/env", {}, token);
}

export async function startRun(token: string, body: RunCreateRequest): Promise<RunRecord> {
  return request<RunRecord>(
    "/api/agitator/runs",
    { method: "POST", body: JSON.stringify(body) },
    token,
  );
}

export async function listRuns(token: string): Promise<RunListResponse> {
  return request<RunListResponse>("/api/agitator/runs", {}, token);
}

export async function getRun(token: string, runId: string): Promise<RunRecord> {
  return request<RunRecord>(`/api/agitator/runs/${runId}`, {}, token);
}

export async function cancelRun(token: string, runId: string): Promise<RunRecord> {
  return request<RunRecord>(`/api/agitator/runs/${runId}/cancel`, { method: "POST" }, token);
}

// --- Phase 7e (PR 4a): AI Chat ---

export async function postChat(token: string, body: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify(body) }, token);
}

// --- Phase 7e (PR 4b): Error Detail ---

export async function getError(token: string, entryId: string): Promise<ErrorDetailResponse> {
  return request<ErrorDetailResponse>(`/api/errors/${encodeURIComponent(entryId)}`, {}, token);
}

// --- Vectorstore Stats tab ---

export async function getChromaStats(token: string): Promise<ChromaStatsResponse> {
  return request<ChromaStatsResponse>("/api/chroma/stats", {}, token);
}

// --- Phase 7e (PR 4b): SSE chat streaming ---

export interface ChatStreamNodeEvent {
  node: string;
  tool_budget_remaining?: number;
  tool_budget_exhausted?: boolean;
  citation_count?: number;
}

export interface ChatStreamCompleteEvent {
  answer: string;
  citations: ChatResponse["citations"];
  session_id: string;
  dry_run: boolean;
  tool_budget_exhausted: boolean;
}

export interface ChatStreamHandlers {
  onNode?: (event: ChatStreamNodeEvent) => void;
  onComplete?: (event: ChatStreamCompleteEvent) => void;
  onError?: (detail: string, status: number) => void;
}

/**
 * Stream a chat response via SSE. Returns an AbortController so the caller
 * can cancel on unmount. Uses `fetch` + ReadableStream because EventSource
 * is GET-only (the chat endpoint takes a JSON body via POST).
 *
 * Pre-flight errors (401, 413) come back as a non-SSE JSON response — they
 * surface through `onError` before any node event fires. Mid-stream
 * upstream-LLM failures arrive as `event: error\ndata: {"detail": "..."}`
 * and also route to `onError`.
 */
export function postChatStream(
  token: string,
  body: ChatRequest,
  handlers: ChatStreamHandlers,
): AbortController {
  const controller = new AbortController();

  void (async () => {
    try {
      const response = await fetch(`${BASE_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ...body, streaming: true }),
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail = `request failed (${response.status})`;
        try {
          const errBody = (await response.json()) as ApiError;
          detail = errBody.detail ?? detail;
        } catch {
          /* non-JSON */
        }
        handlers.onError?.(detail, response.status);
        return;
      }

      if (!response.body) {
        handlers.onError?.("response body missing", 0);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      const dispatch = (block: string) => {
        const parsed = parseSseBlock(block);
        if (!parsed) return;
        if (parsed.event === "node") {
          handlers.onNode?.(parsed.data as ChatStreamNodeEvent);
        } else if (parsed.event === "complete") {
          handlers.onComplete?.(parsed.data as ChatStreamCompleteEvent);
        } else if (parsed.event === "error") {
          const detail = (parsed.data as { detail?: string }).detail ?? "stream error";
          handlers.onError?.(detail, 0);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        // Keep the final (possibly incomplete) chunk in the buffer.
        buffer = parts.pop() ?? "";
        for (const part of parts) dispatch(part);
      }
      // Flush any trailing partial UTF-8 + dispatch a final event that
      // arrived without a `\n\n` terminator. Uvicorn sometimes closes the
      // stream after the last byte without a final blank line — without
      // this the `complete` event would silently vanish.
      buffer += decoder.decode();
      if (buffer.trim()) dispatch(buffer);
    } catch (err) {
      if ((err as { name?: string }).name === "AbortError") return;
      handlers.onError?.((err as Error).message ?? "stream failed", 0);
    }
  })();

  return controller;
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  const trimmed = block.trim();
  if (!trimmed) return null;
  let event = "";
  const dataLines: string[] = [];
  for (const line of trimmed.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  if (!event || dataLines.length === 0) return null;
  try {
    // Per the WHATWG SSE spec, multi-line `data:` fields are joined by
    // newline (not by concatenation). Our backend emits single-line JSON
    // today, but joining with `\n` is forward-compat for pretty-printed
    // payloads — and a 1-char fix.
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}
