import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { LogsFilterBar, type FilterState } from "../components/LogsFilterBar";
import { LogsTable } from "../components/LogsTable";
import { getLogs, HttpError, searchLogs } from "../lib/api";
import { resolveTimeWindow } from "../lib/time-window";
import { useAuth } from "../lib/auth";
import { APP_NAMES, LOG_LEVELS, type AppName, type LogEntry } from "../types/logs";

const PAGE_LIMIT = 100;
const SEARCH_TOP_K = 50;
const SEARCH_DEBOUNCE_MS = 300;

function isAppName(value: string): value is AppName {
  return (APP_NAMES as readonly string[]).includes(value);
}

function initialFilters(presetApp: string | null): FilterState {
  const apps: AppName[] = presetApp && isAppName(presetApp) ? [presetApp] : [...APP_NAMES];
  return {
    apps,
    levels: [...LOG_LEVELS],
    window: "1h",
    customSince: null,
    customUntil: null,
    query: "",
  };
}

export function LogExplorer() {
  const { token, logout } = useAuth();
  const [searchParams] = useSearchParams();
  const presetApp = searchParams.get("app");

  const [filters, setFilters] = useState<FilterState>(() => initialFilters(presetApp));
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [scores, setScores] = useState<number[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // v1.1.2 — surfaced from the search response when the backend's
  // backfill task is still populating Chroma. Shows an "indexing in
  // progress" hint above the empty-state row so a cold-start blank
  // result doesn't read as "no matches".
  const [partialCorpus, setPartialCorpus] = useState(false);

  // Debounce the search input so every keystroke doesn't trigger an embedding
  // round-trip. 300ms feels responsive but coalesces typing bursts.
  const [debouncedQuery, setDebouncedQuery] = useState(filters.query);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(filters.query), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [filters.query]);

  const { since, until } = useMemo(
    () => resolveTimeWindow(filters.window, filters.customSince, filters.customUntil),
    [filters.window, filters.customSince, filters.customUntil],
  );
  const isSearchMode = debouncedQuery.trim().length > 0;

  const fetchPage = useCallback(
    async (before: string | null, append: boolean) => {
      if (!token) return;
      setLoading(true);
      try {
        if (isSearchMode) {
          const res = await searchLogs(token, {
            query: debouncedQuery,
            apps: filters.apps,
            levels: filters.levels,
            since,
            before: until,
            top_k: SEARCH_TOP_K,
          });
          setEntries(res.entries);
          setScores(res.scores);
          setPartialCorpus(Boolean(res.partial_corpus));
          setNextBefore(null);
        } else {
          // Cursor pagination uses `before` for the timestamp cursor. The
          // custom-window upper bound is sent as `until` so the backend AND's
          // it with the cursor — pagination and time-window stay orthogonal.
          const res = await getLogs(token, {
            apps: filters.apps,
            levels: filters.levels,
            since,
            until,
            before,
            limit: PAGE_LIMIT,
          });
          setEntries((prev) => (append ? [...prev, ...res.entries] : res.entries));
          setScores([]);
          setPartialCorpus(false);
          setNextBefore(res.next_before);
        }
        setError(null);
      } catch (err) {
        if (err instanceof HttpError && err.status === 401) {
          logout();
          return;
        }
        if (err instanceof HttpError && err.status === 503 && isSearchMode) {
          // v1.1.2 Option A — surface the backend's exact 503 detail. The
          // search router now distinguishes "models still loading" (cold-deploy
          // window, message says "warming up — try again in a minute") from
          // "Ollama unreachable" (config error, message names OLLAMA_BASE_URL).
          // Using the wire detail keeps frontend + backend strings in lockstep.
          setError(err.detail);
        } else if (err instanceof HttpError) {
          setError(`${isSearchMode ? "search" : "logs"} request failed (${err.status})`);
        } else {
          setError(`${isSearchMode ? "search" : "logs"} request failed`);
        }
      } finally {
        setLoading(false);
      }
    },
    [token, logout, filters.apps, filters.levels, since, until, isSearchMode, debouncedQuery],
  );

  // Refetch from page 1 whenever filters change (or the debounced query
  // changes, since fetchPage closes over it).
  useEffect(() => {
    void fetchPage(null, false);
  }, [fetchPage]);

  function onLoadMore() {
    if (nextBefore) void fetchPage(nextBefore, true);
  }

  return (
    <section aria-labelledby="logs-heading" className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 id="logs-heading" className="text-lg font-semibold text-slate-900">
          Log Explorer
        </h2>
        <button
          type="button"
          onClick={() => void fetchPage(null, false)}
          disabled={loading}
          className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <LogsFilterBar value={filters} onChange={setFilters} />
      {error && (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {isSearchMode && partialCorpus && !loading && (
        <p
          role="status"
          data-testid="partial-corpus-hint"
          className="rounded-md bg-amber-50 p-3 text-sm text-amber-800"
        >
          Indexing still in progress — semantic search results may be incomplete.
        </p>
      )}
      <LogsTable
        entries={entries}
        scores={scores}
        loading={loading}
        hasMore={!isSearchMode && nextBefore !== null}
        onLoadMore={onLoadMore}
      />
    </section>
  );
}
