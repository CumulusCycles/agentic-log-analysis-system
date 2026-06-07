import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyCorpusBanner } from "../components/EmptyCorpusBanner";
import { ProactiveFindingsPanel } from "../components/ProactiveFindingsPanel";
import { StatusCard } from "../components/StatusCard";
import { usePolling } from "../hooks/use-polling";
import { getStatus, getStatusHistory, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { StatusHistoryResponse, StatusResponse, TimeWindow } from "../types/logs";

const STATUS_POLL_INTERVAL_MS = 15_000;
// History is heavier (4-volume scan + bucketing) — poll slower than the
// status counts above.
const HISTORY_POLL_INTERVAL_MS = 60_000;

const HISTORY_WINDOWS: readonly TimeWindow[] = ["1h", "24h", "7d"] as const;

export function Overview() {
  const { token, logout } = useAuth();
  const [data, setData] = useState<StatusResponse | null>(null);
  const [history, setHistory] = useState<StatusHistoryResponse | null>(null);
  const [historyWindow, setHistoryWindow] = useState<TimeWindow>("24h");
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

  const refreshHistory = useCallback(async () => {
    if (!token) return;
    try {
      const next = await getStatusHistory(token, historyWindow);
      setHistory(next);
    } catch (err) {
      if (err instanceof HttpError && err.status === 401) {
        logout();
        return;
      }
      // Silent on transient history failures — the page is still usable from
      // the /api/status data; surfacing a banner for the sparklines would
      // overweight a low-stakes view.
    }
  }, [token, logout, historyWindow]);

  usePolling(refresh, STATUS_POLL_INTERVAL_MS);
  usePolling(refreshHistory, HISTORY_POLL_INTERVAL_MS);

  // `usePolling` captures its `fn` in a ref so changing `historyWindow`'s
  // closure doesn't fire `refreshHistory` immediately — only the next 60s
  // tick would pick up the new window. This first-render-guarded effect
  // kicks the refetch when the closure reference changes, skipping the
  // initial render to avoid double-firing with usePolling's mount tick.
  // See `reference_use_polling_ref_capture_gap` memory.
  const isFirstHistoryRender = useRef(true);
  useEffect(() => {
    if (isFirstHistoryRender.current) {
      isFirstHistoryRender.current = false;
      return;
    }
    void refreshHistory();
  }, [refreshHistory]);

  if (error && !data) {
    return (
      <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
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
        <h2 id="overview-heading" className="text-lg font-semibold text-slate-900">
          Overview
        </h2>
        <span className="text-xs text-slate-500" data-testid="as-of">
          updated {asOf}
        </span>
      </div>
      {error && (
        <p role="alert" className="mt-2 rounded-md bg-amber-50 p-2 text-xs text-amber-800">
          {error} — showing cached data
        </p>
      )}
      {data.corpus_empty && <EmptyCorpusBanner />}
      <ProactiveFindingsPanel
        findings={data.proactive_findings ?? []}
        scanEnabled={data.scan_enabled ?? false}
        lastScanAt={data.last_scan_at ?? null}
      />

      <fieldset
        className="mt-4 flex items-center gap-3"
        aria-label="Trend chart window"
        data-testid="history-window-selector"
      >
        <legend className="text-xs font-medium text-slate-600">Trend window</legend>
        {HISTORY_WINDOWS.map((w) => (
          <label key={w} className="flex items-center gap-1 text-xs text-slate-700">
            <input
              type="radio"
              name="overview-history-window"
              value={w}
              checked={historyWindow === w}
              onChange={() => setHistoryWindow(w)}
              data-testid={`history-window-${w}`}
            />
            <span>{w}</span>
          </label>
        ))}
      </fieldset>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="status-grid">
        {data.apps.map((app) => (
          <StatusCard key={app.name} status={app} history={history?.apps[app.name] ?? []} />
        ))}
      </div>
    </section>
  );
}
