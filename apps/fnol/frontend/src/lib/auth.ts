import { createContext, useContext } from "react";

import type { JwtClaims } from "../types/api";

export interface AuthState {
  token: string | null;
  claims: JwtClaims | null;
}

export interface AuthContextValue extends AuthState {
  setToken: (token: string | null) => void;
  logout: () => void;
}

export const STORAGE_KEY = "fnol_token";

export const AuthContext = createContext<AuthContextValue | null>(null);

function base64urlDecode(segment: string): string {
  const b64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  // atob requires the input length to be a multiple of 4; base64url drops
  // padding, so re-pad with '=' before decoding.
  const pad = b64.length % 4;
  const padded = pad === 0 ? b64 : b64 + "=".repeat(4 - pad);
  return atob(padded);
}

export function decodeJwt(token: string): JwtClaims | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const json = base64urlDecode(parts[1]);
    return JSON.parse(json) as JwtClaims;
  } catch {
    return null;
  }
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
