import { useCallback, useState } from "react";

import { BarChart, type BarChartDatum } from "../components/BarChart";
import { usePolling } from "../hooks/use-polling";
import { getChromaStats, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { ChromaStatsResponse } from "../types/vectorstore";

const POLL_INTERVAL_MS = 30_000;

export function VectorstoreStats() {
  const { token, logout } = useAuth();
  const [data, setData] = useState<ChromaStatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const next = await getChromaStats(token);
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
  }, [token, logout]);

  usePolling(refresh, POLL_INTERVAL_MS);

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

      <Section title="By day (last 30 days)" hint="UTC dates">
        <BarChart data={byDay} accent="slate" ariaLabel="By day" emptyHint="No day data." />
      </Section>
    </section>
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
