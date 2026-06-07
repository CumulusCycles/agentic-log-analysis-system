import { type TimeWindowPreset } from "../lib/time-window";
import { APP_NAMES, LOG_LEVELS, type AppName, type LogLevel } from "../types/logs";
import { TimeWindowSelector } from "./TimeWindowSelector";

export interface FilterState {
  apps: AppName[];
  levels: LogLevel[];
  window: TimeWindowPreset;
  customSince: string | null;
  customUntil: string | null;
  query: string;
}

interface Props {
  value: FilterState;
  onChange: (next: FilterState) => void;
}

function toggle<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

export function LogsFilterBar({ value, onChange }: Props) {
  function setApps(apps: AppName[]) {
    onChange({ ...value, apps });
  }
  function setLevels(levels: LogLevel[]) {
    onChange({ ...value, levels });
  }
  function setQuery(query: string) {
    onChange({ ...value, query });
  }

  return (
    <section
      aria-label="filters"
      className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200"
    >
      <div className="mb-4">
        <label
          htmlFor="filter-query"
          className="block text-xs font-semibold uppercase tracking-wide text-slate-500"
        >
          Semantic search
        </label>
        <input
          id="filter-query"
          type="search"
          placeholder="auth failures, upstream errors, claim_validation_rejected…"
          value={value.query}
          onChange={(e) => setQuery(e.target.value)}
          data-testid="filter-query"
          className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm placeholder:text-slate-400 focus:border-slate-500 focus:outline-none"
        />
        {value.query && (
          <p className="mt-1 text-[11px] text-slate-500">
            Semantic search uses the Chroma vector store — time-window filter limits results to that
            range; cursor pagination is disabled.
          </p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <fieldset>
          <div className="flex items-baseline justify-between">
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              App
            </legend>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setApps([...APP_NAMES])}
                data-testid="filter-app-check-all"
                className="text-[11px] text-slate-500 underline hover:text-slate-700"
              >
                Check all
              </button>
              <span className="text-[11px] text-slate-300">·</span>
              <button
                type="button"
                onClick={() => setApps([])}
                data-testid="filter-app-clear-all"
                className="text-[11px] text-slate-500 underline hover:text-slate-700"
              >
                Clear all
              </button>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {APP_NAMES.map((app) => (
              <label
                key={app}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
              >
                <input
                  type="checkbox"
                  checked={value.apps.includes(app)}
                  onChange={() => setApps(toggle(value.apps, app))}
                  data-testid={`filter-app-${app}`}
                />
                {app}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <div className="flex items-baseline justify-between">
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Level
            </legend>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setLevels([...LOG_LEVELS])}
                data-testid="filter-level-check-all"
                className="text-[11px] text-slate-500 underline hover:text-slate-700"
              >
                Check all
              </button>
              <span className="text-[11px] text-slate-300">·</span>
              <button
                type="button"
                onClick={() => setLevels([])}
                data-testid="filter-level-clear-all"
                className="text-[11px] text-slate-500 underline hover:text-slate-700"
              >
                Clear all
              </button>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {LOG_LEVELS.map((lvl) => (
              <label
                key={lvl}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
              >
                <input
                  type="checkbox"
                  checked={value.levels.includes(lvl)}
                  onChange={() => setLevels(toggle(value.levels, lvl))}
                  data-testid={`filter-level-${lvl}`}
                />
                {lvl}
              </label>
            ))}
          </div>
        </fieldset>
        <TimeWindowSelector
          value={value.window}
          customSince={value.customSince}
          customUntil={value.customUntil}
          onChange={(next) =>
            onChange({
              ...value,
              window: next.preset,
              customSince: next.customSince,
              customUntil: next.customUntil,
            })
          }
          idPrefix="filter-window"
        />
      </div>
    </section>
  );
}
