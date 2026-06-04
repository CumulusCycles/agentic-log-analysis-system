import { Link } from "react-router-dom";

import type { AppStatus } from "../types/logs";

import { StatusBadge } from "./StatusBadge";

function formatLastSeen(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    month: "short",
    day: "numeric",
  });
}

function CountsRow({
  label,
  info,
  warn,
  error,
}: {
  label: string;
  info: number;
  warn: number;
  error: number;
}) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-500">{label}</span>
      <div className="flex items-center gap-2 font-mono">
        <span className="text-blue-700">{info}</span>
        <span className="text-slate-300">·</span>
        <span className="text-amber-700">{warn}</span>
        <span className="text-slate-300">·</span>
        <span className="text-red-700">{error}</span>
      </div>
    </div>
  );
}

export function StatusCard({ status }: { status: AppStatus }) {
  return (
    <Link
      to={`/logs?app=${encodeURIComponent(status.name)}`}
      data-testid="status-card"
      data-app={status.name}
      className="block rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 transition hover:ring-slate-400"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">{status.name}</h3>
        <StatusBadge status={status.status} />
      </div>
      <p className="mt-1 text-xs text-slate-500">
        last seen {formatLastSeen(status.last_seen_at)}
      </p>
      <div className="mt-4 space-y-1.5">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wide text-slate-400">
          <span>window</span>
          <span>info · warn · err</span>
        </div>
        <CountsRow
          label="1 hour"
          info={status.counts_1h.info}
          warn={status.counts_1h.warn}
          error={status.counts_1h.error}
        />
        <CountsRow
          label="24 hours"
          info={status.counts_24h.info}
          warn={status.counts_24h.warn}
          error={status.counts_24h.error}
        />
        <CountsRow
          label="7 days"
          info={status.counts_7d.info}
          warn={status.counts_7d.warn}
          error={status.counts_7d.error}
        />
      </div>
    </Link>
  );
}
