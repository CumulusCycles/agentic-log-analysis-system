// Lightweight fetch wrapper. Production: relative paths (same origin as the
// Express host). Dev: VITE_CUSTOMER_PORTAL_API_BASE_URL points at
// http://localhost:3001.

import type {
  ApiError,
  ClaimOut,
  LoginRequest,
  PolicyOut,
  TokenResponse,
  UserOut,
} from "../types/api";

const BASE_URL = import.meta.env.VITE_CUSTOMER_PORTAL_API_BASE_URL ?? "";

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
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getProfile(token: string): Promise<UserOut> {
  return request<UserOut>("/profile/me", {}, token);
}

export async function getPolicies(token: string): Promise<PolicyOut[]> {
  return request<PolicyOut[]>("/policies/me", {}, token);
}

export async function getClaims(token: string): Promise<ClaimOut[]> {
  return request<ClaimOut[]>("/claims/me", {}, token);
}
