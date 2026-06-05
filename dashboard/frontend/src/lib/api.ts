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
import type {
  LogsFilters,
  LogsResponse,
  LogsSearchRequest,
  LogsSearchResponse,
  StatusResponse,
} from "../types/logs";

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
