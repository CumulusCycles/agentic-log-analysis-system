import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BarChart, type BarChartDatum } from "../components/BarChart";
import { TimeWindowSelector } from "../components/TimeWindowSelector";
import { usePolling } from "../hooks/use-polling";
import { flushChroma, getChromaStats, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { resolveTimeWindow, type TimeWindowPreset } from "../lib/time-window";
import type { ChromaStatsResponse } from "../types/vectorstore";

const POLL_INTERVAL_MS = 30_000;

// Window labels for the "By day" card header. Mirrors the preset table in
// TimeWindowSelector so the header stays in lockstep with the radio choice.
const WINDOW_LABELS: Record<TimeWindowPreset, string> = {
  "1h": "last 1 hour",
  "24h": "last 24 hours",
  "7d": "last 7 days",
  custom: "custom range",
};

export function VectorstoreStats() {
  const { token, logout } = useAuth();
  const [data, setData] = useState<ChromaStatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  // Default to 7d so the chart matches the typical operator question
  // ("what got embedded recently?") without dumping a 30-day strip.
  const [window, setWindow] = useState<TimeWindowPreset>("7d");
  const [customSince, setCustomSince] = useState<string | null>(null);
  const [customUntil, setCustomUntil] = useState<string | null>(null);

  const { since, until } = useMemo(
    () => resolveTimeWindow(window, customSince, customUntil),
    [window, customSince, customUntil],
  );

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const next = await getChromaStats(token, { since, until });
      setData(next);
      setError(null);
      setUnavailable(false);
    } catch (err) {
      if (err instanceof HttpError && err.status === 401) {
        logout();
        return;
      }
      if (err instanceof HttpError && err.status === 503) {
        setUnavailable(true);
        return;
      }
      if (err instanceof HttpError) {
        setError(`stats request failed (${err.status})`);
      } else {
        setError("stats request failed");
      }
    }
  }, [token, logout, since, until]);

  usePolling(refresh, POLL_INTERVAL_MS);

  // Refetch immediately when the operator changes the by_day window — the
  // 30s polling loop captures `refresh` in a ref and only fires on its own
  // interval, so an explicit kick is needed for a snappy UI. Skip the first
  // run so we don't double-fire with usePolling's mount tick.
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    void refresh();
  }, [refresh]);

  const handleFlushed = useCallback(() => {
    void refresh();
  }, [refresh]);

  if (unavailable) {
    return (
      <section aria-labelledby="vectorstore-heading">
        <h2 id="vectorstore-heading" className="text-lg font-semibold text-slate-900">
          Vectorstore Stats
        </h2>
        <p role="alert" className="mt-4 rounded-md bg-amber-50 p-4 text-sm text-amber-800">
          Vectorstore is unavailable. Check that <code>OPENAI_API_KEY</code> is set in{" "}
          <code>.env</code> and that the dashboard container has been restarted.
        </p>
      </section>
    );
  }

  if (error && !data) {
    return (
      <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!data) {
    return <div className="text-sm text-slate-500">Loading stats…</div>;
  }

  const asOf = new Date(data.as_of).toLocaleString();

  const byApp: BarChartDatum[] = Object.entries(data.by_app).map(([label, value]) => ({
    label,
    value,
  }));
  const byLevel: BarChartDatum[] = Object.entries(data.by_level).map(([label, value]) => ({
    label,
    value,
  }));
  const bySource: BarChartDatum[] = Object.entries(data.by_source).map(([label, value]) => ({
    label,
    value,
  }));
  const byEvent: BarChartDatum[] = data.by_event.map((e) => ({
    label: e.event,
    value: e.count,
  }));
  const byDay: BarChartDatum[] = data.by_day.map((d) => ({
    // Show only MM-DD in the chart to keep the left column narrow.
    label: d.date.slice(5),
    value: d.count,
  }));

  return (
    <section aria-labelledby="vectorstore-heading" className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h2 id="vectorstore-heading" className="text-lg font-semibold text-slate-900">
          Vectorstore Stats
        </h2>
        <span className="text-xs text-slate-500" data-testid="as-of">
          updated {asOf}
        </span>
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-amber-50 p-2 text-xs text-amber-800">
          {error} — showing cached data
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard label="Total embedded documents" value={data.total_count.toLocaleString()} />
        <SummaryCard label="Embedding model" value={data.embedding_model} />
        <SummaryCard label="Vector dimensions" value={data.dimensions.toLocaleString()} />
      </div>

      <FlushPanel totalCount={data.total_count} onFlushed={handleFlushed} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="By app" hint="Embedded documents per source app">
          <BarChart data={byApp} accent="blue" ariaLabel="By app" emptyHint="No app data." />
        </Section>
        <Section title="By level" hint="Only WARN + ERROR pass the ingest gate by default">
          <BarChart data={byLevel} accent="rose" ariaLabel="By level" emptyHint="No level data." />
        </Section>
        <Section title="By source" hint="X-Source provenance per ADR-011">
          <BarChart
            data={bySource}
            accent="emerald"
            ariaLabel="By source"
            emptyHint="No source data."
          />
        </Section>
        <Section title="Top events" hint="Top 10 most-embedded event names">
          <BarChart
            data={byEvent}
            accent="amber"
            ariaLabel="Top events"
            emptyHint="No event data yet."
          />
        </Section>
      </div>

      <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-baseline justify-between">
          <h3 className="text-sm font-semibold text-slate-900">By day ({WINDOW_LABELS[window]})</h3>
          <span className="text-xs text-slate-500">UTC dates</span>
        </div>
        <div className="mb-3">
          <TimeWindowSelector
            value={window}
            customSince={customSince}
            customUntil={customUntil}
            onChange={(next) => {
              setWindow(next.preset);
              setCustomSince(next.customSince);
              setCustomUntil(next.customUntil);
            }}
            idPrefix="stats-window"
          />
        </div>
        <BarChart data={byDay} accent="slate" ariaLabel="By day" emptyHint="No day data." />
      </div>
    </section>
  );
}

// text-embedding-3-small list price (2026-Q1) — keeps the UI estimate consistent
// with the backend's _OPENAI_EMBEDDING_USD_PER_TOKEN constant. The 80
// tokens-per-doc figure is an order-of-magnitude approximation calibrated
// against this project's typical structured log line; it's labelled as
// approximate in the UI so the operator doesn't mistake it for an invoice.
const ESTIMATED_TOKENS_PER_DOC = 80;
const USD_PER_TOKEN = 0.02 / 1_000_000;

function estimateRefillCost(totalCount: number): string {
  const usd = totalCount * ESTIMATED_TOKENS_PER_DOC * USD_PER_TOKEN;
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return "less than $0.01";
  return `~$${usd.toFixed(2)}`;
}

interface FlushPanelProps {
  totalCount: number;
  onFlushed: () => void;
}

function FlushPanel({ totalCount, onFlushed }: FlushPanelProps) {
  const { token, logout } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ deleted: number; at: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refillEstimate = useMemo(() => estimateRefillCost(totalCount), [totalCount]);

  const performFlush = useCallback(async () => {
    if (!token) return;
    setPending(true);
    setError(null);
    try {
      const response = await flushChroma(token);
      setResult({ deleted: response.deleted_count, at: response.as_of });
      setConfirming(false);
      onFlushed();
    } catch (err) {
      if (err instanceof HttpError && err.status === 401) {
        logout();
        return;
      }
      if (err instanceof HttpError) {
        setError(`flush failed (${err.status})`);
      } else {
        setError("flush failed");
      }
    } finally {
      setPending(false);
    }
  }, [token, logout, onFlushed]);

  return (
    <div
      className="rounded-md border border-amber-200 bg-amber-50 p-4 shadow-sm"
      data-testid="flush-panel"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="text-sm">
          <h3 className="font-semibold text-amber-900">Vectorstore maintenance</h3>
          <p className="mt-1 text-amber-800">
            Delete every embedded document. The collection is preserved (same name + embedding
            model) — only the docs are removed.
          </p>
        </div>
        {!confirming && (
          <button
            type="button"
            onClick={() => {
              setError(null);
              setResult(null);
              setConfirming(true);
            }}
            disabled={pending || totalCount === 0}
            className="shrink-0 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="flush-button"
          >
            Flush vectorstore…
          </button>
        )}
      </div>

      {confirming && (
        <div
          className="mt-3 rounded-md border border-rose-300 bg-white p-3 text-sm text-slate-800"
          data-testid="flush-confirm"
          role="alertdialog"
          aria-labelledby="flush-confirm-title"
        >
          <p id="flush-confirm-title" className="font-semibold text-rose-900">
            Delete all {totalCount.toLocaleString()} embedded documents?
          </p>
          <p className="mt-1 text-slate-700">
            Re-embedding from the log volumes is estimated at <strong>{refillEstimate}</strong> in
            OpenAI charges (~
            {ESTIMATED_TOKENS_PER_DOC} tokens per doc × text-embedding-3-small list price). Backfill
            runs at startup only — to repopulate, run{" "}
            <code className="rounded bg-slate-100 px-1">docker compose restart log-dashboard</code>{" "}
            after the flush completes.
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={performFlush}
              disabled={pending}
              className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="flush-confirm-button"
            >
              {pending ? "Flushing…" : "Yes, delete everything"}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={pending}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed"
              data-testid="flush-cancel-button"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {result && !confirming && (
        <p
          className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-800"
          role="status"
          data-testid="flush-result"
        >
          Deleted {result.deleted.toLocaleString()} document
          {result.deleted === 1 ? "" : "s"}. To repopulate, restart the dashboard:{" "}
          <code className="rounded bg-white px-1">docker compose restart log-dashboard</code>
        </p>
      )}

      {error && (
        <p
          className="mt-3 rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800"
          role="alert"
          data-testid="flush-error"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold text-slate-900" title={value}>
        {value}
      </div>
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {hint && <span className="text-xs text-slate-500">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
