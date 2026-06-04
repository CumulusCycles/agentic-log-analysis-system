import { useCallback, useState } from "react";

import { StatusCard } from "../components/StatusCard";
import { usePolling } from "../hooks/use-polling";
import { getStatus, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { StatusResponse } from "../types/logs";

const POLL_INTERVAL_MS = 15_000;

export function Overview() {
  const { token, logout } = useAuth();
  const [data, setData] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const next = await getStatus(token);
      setData(next);
      setError(null);
    } catch (err) {
      if (err instanceof HttpError && err.status === 401) {
        // Stale or expired session — clear the token; RequireAuth bounces to /login.
        logout();
        return;
      }
      if (err instanceof HttpError) {
        setError(`status request failed (${err.status})`);
      } else {
        setError("status request failed");
      }
    }
  }, [token, logout]);

  usePolling(refresh, POLL_INTERVAL_MS);

  if (error && !data) {
    return (
      <div
        role="alert"
        className="rounded-md bg-red-50 p-4 text-sm text-red-700"
      >
        {error}
      </div>
    );
  }

  if (!data) {
    return <div className="text-sm text-slate-500">Loading status…</div>;
  }

  const asOf = new Date(data.as_of).toLocaleString();

  return (
    <section aria-labelledby="overview-heading">
      <div className="flex items-baseline justify-between">
        <h2
          id="overview-heading"
          className="text-lg font-semibold text-slate-900"
        >
          Overview
        </h2>
        <span className="text-xs text-slate-500" data-testid="as-of">
          updated {asOf}
        </span>
      </div>
      {error && (
        <p
          role="alert"
          className="mt-2 rounded-md bg-amber-50 p-2 text-xs text-amber-800"
        >
          {error} — showing cached data
        </p>
      )}
      <div
        className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        data-testid="status-grid"
      >
        {data.apps.map((app) => (
          <StatusCard key={app.name} status={app} />
        ))}
      </div>
    </section>
  );
}
