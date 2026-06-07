// Lightweight fetch wrapper. Production: relative paths (same origin as the
// Spring Boot host). Dev: VITE_AGENT_PORTAL_API_BASE_URL points at
// http://localhost:8081. All paths use the /api/* prefix so React Router
// owns the top-level routes (/claims, /profile, /login) in the SPA.

import type {
  ApiError,
  ClaimDetail,
  ClaimOut,
  LoginRequest,
  TokenResponse,
  UserOut,
} from "../types/api";

const BASE_URL = import.meta.env.VITE_AGENT_PORTAL_API_BASE_URL ?? "";

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
  // ADR-011 2026-06-07 amendment: SPAs explicitly tag `prod` so the
  // dashboard's `by_source` bucket means "real human action through this
  // SPA," not "header absent." Single seam — every outbound call sets it.
  headers.set("X-Source", "prod");
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

export async function getProfile(token: string): Promise<UserOut> {
  return request<UserOut>("/api/profile/me", {}, token);
}

export async function getClaims(token: string): Promise<ClaimOut[]> {
  return request<ClaimOut[]>("/api/claims", {}, token);
}

export async function getClaim(token: string, id: string): Promise<ClaimDetail> {
  return request<ClaimDetail>(`/api/claims/${encodeURIComponent(id)}`, {}, token);
}
