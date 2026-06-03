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

export const STORAGE_KEY = "customer_portal_token";

export const AuthContext = createContext<AuthContextValue | null>(null);

export function decodeJwt(token: string): JwtClaims | null {
  try {
    const [, payload] = token.split(".");
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
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
