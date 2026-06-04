import {
  APP_NAMES,
  LOG_LEVELS,
  type AppName,
  type LogLevel,
  type TimeWindow,
} from "../types/logs";

export interface FilterState {
  apps: AppName[];
  levels: LogLevel[];
  window: TimeWindow;
}

interface Props {
  value: FilterState;
  onChange: (next: FilterState) => void;
}

const WINDOWS: { id: TimeWindow; label: string }[] = [
  { id: "1h", label: "Last 1h" },
  { id: "24h", label: "Last 24h" },
  { id: "7d", label: "Last 7d" },
];

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
  function setWindow(window: TimeWindow) {
    onChange({ ...value, window });
  }

  return (
    <section
      aria-label="filters"
      className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200"
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <fieldset>
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            App
          </legend>
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
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Level
          </legend>
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
        <fieldset>
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Time window
          </legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {WINDOWS.map((w) => (
              <label
                key={w.id}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
              >
                <input
                  type="radio"
                  name="time-window"
                  checked={value.window === w.id}
                  onChange={() => setWindow(w.id)}
                  data-testid={`filter-window-${w.id}`}
                />
                {w.label}
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </section>
  );
}
