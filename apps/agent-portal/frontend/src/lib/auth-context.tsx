import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  AuthContext,
  decodeJwt,
  STORAGE_KEY,
  type AuthContextValue,
  type AuthState,
} from "./auth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const token =
      typeof window === "undefined" ? null : localStorage.getItem(STORAGE_KEY);
    return { token, claims: token ? decodeJwt(token) : null };
  });

  useEffect(() => {
    if (state.token) {
      localStorage.setItem(STORAGE_KEY, state.token);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [state.token]);

  const setToken = useCallback((token: string | null) => {
    setState({ token, claims: token ? decodeJwt(token) : null });
  }, []);

  const logout = useCallback(() => setToken(null), [setToken]);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, setToken, logout }),
    [state, setToken, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
