import { Fragment, useState } from "react";

import type { LogEntry } from "../types/logs";

import { LevelPill } from "./LevelPill";

function formatTs(iso: string): string {
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

function ExpandedRow({ entry, colSpan }: { entry: LogEntry; colSpan: number }) {
  const fieldEntries = Object.entries(entry.fields);
  return (
    <tr data-testid="log-row-expanded" className="bg-slate-50">
      <td colSpan={colSpan} className="px-4 py-3">
        <div className="space-y-3 text-xs">
          {fieldEntries.length > 0 && (
            <div>
              <h4 className="font-semibold text-slate-600">Fields</h4>
              <dl className="mt-1 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
                {fieldEntries.map(([key, val]) => (
                  <div key={key} className="flex gap-2">
                    <dt className="font-mono text-slate-500">{key}</dt>
                    <dd className="font-mono text-slate-800 break-all">
                      {typeof val === "string" ? val : JSON.stringify(val)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          <div>
            <h4 className="font-semibold text-slate-600">Raw</h4>
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all rounded bg-slate-900 p-2 font-mono text-[11px] text-slate-100">
              {entry.raw}
            </pre>
          </div>
        </div>
      </td>
    </tr>
  );
}

interface Props {
  entries: LogEntry[];
  loading: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  // 7d semantic-search scores, parallel to `entries`. Empty/absent in
  // substring-filter mode (Phase 7b /api/logs path).
  scores?: number[];
}

export function LogsTable({ entries, loading, hasMore, onLoadMore, scores }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const showScores = (scores?.length ?? 0) > 0;

  if (!loading && entries.length === 0) {
    return (
      <p className="rounded-md bg-white p-4 text-sm text-slate-500 ring-1 ring-slate-200">
        No entries match these filters.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-4 py-2 text-left">
              Time
            </th>
            <th scope="col" className="px-4 py-2 text-left">
              App
            </th>
            <th scope="col" className="px-4 py-2 text-left">
              Level
            </th>
            <th scope="col" className="px-4 py-2 text-left">
              Event
            </th>
            {showScores && (
              <th scope="col" className="px-4 py-2 text-right" data-testid="score-header">
                Score
              </th>
            )}
            <th scope="col" className="px-4 py-2 text-right">
              <span className="sr-only">Expand</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {entries.map((entry, idx) => {
            const isExpanded = expandedId === entry.id;
            const score = scores?.[idx];
            return (
              <Fragment key={entry.id}>
                <tr
                  data-testid="log-row"
                  data-app={entry.app}
                  data-level={entry.level}
                  className="cursor-pointer hover:bg-slate-50"
                  onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                >
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-500">
                    {formatTs(entry.timestamp)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-slate-700">
                    {entry.app}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2">
                    <LevelPill level={entry.level} />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-slate-800">{entry.event}</td>
                  {showScores && (
                    <td
                      className="whitespace-nowrap px-4 py-2 text-right font-mono text-xs text-slate-500"
                      data-testid="score-cell"
                    >
                      {score !== undefined ? score.toFixed(3) : "—"}
                    </td>
                  )}
                  <td className="px-4 py-2 text-right text-xs text-slate-400">
                    {isExpanded ? "▾" : "▸"}
                  </td>
                </tr>
                {isExpanded && <ExpandedRow entry={entry} colSpan={showScores ? 6 : 5} />}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3 text-xs">
        <span className="text-slate-500">
          {entries.length} entr{entries.length === 1 ? "y" : "ies"}
        </span>
        {hasMore && (
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loading}
            data-testid="load-more"
            className="rounded-md border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load more"}
          </button>
        )}
      </div>
    </div>
  );
}
