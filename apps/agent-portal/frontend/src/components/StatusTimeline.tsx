import type { ClaimStatusHistoryOut } from "../types/api";

export function StatusTimeline({
  history,
}: {
  history: ClaimStatusHistoryOut[];
}) {
  if (history.length === 0) {
    return <p className="text-sm text-slate-600">No status history.</p>;
  }
  return (
    <ol className="space-y-3" data-testid="status-timeline">
      {history.map((entry, idx) => (
        <li
          key={`${entry.changed_at}-${idx}`}
          className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3"
        >
          <div className="flex flex-wrap items-baseline gap-2 text-sm">
            <span className="font-mono text-xs text-slate-500">
              {new Date(entry.changed_at).toLocaleString()}
            </span>
            <span className="font-medium text-slate-900">
              {entry.from_status ?? "—"} → {entry.to_status}
            </span>
            <span className="text-xs text-slate-500">by {entry.actor_id}</span>
          </div>
          {entry.note && (
            <p className="mt-1 text-sm text-slate-700">{entry.note}</p>
          )}
        </li>
      ))}
    </ol>
  );
}
