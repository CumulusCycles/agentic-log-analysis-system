import { useCallback, useEffect, useMemo, useState } from "react";

import { usePolling } from "../hooks/use-polling";
import {
  cancelRun,
  getAgitatorEnv,
  HttpError,
  listRuns,
  listScenarios,
  startRun,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import type { AgitatorEnv, RunRecord, ScenarioSpec } from "../types/agitator";

const ACTIVE_POLL_MS = 1500;
const IDLE_POLL_MS = 5000;
// How many recent runs to surface inline on each scenario card. The Agitator
// ring buffer holds 50 globally; per-scenario the last 5 is plenty of signal
// without making the card scroll.
const PER_CARD_RUN_LIMIT = 5;

interface ParamState {
  [paramName: string]: number;
}

function buildDefaultParams(spec: ScenarioSpec): ParamState {
  return spec.params.reduce<ParamState>((acc, p) => {
    acc[p.name] = p.default;
    return acc;
  }, {});
}

// Newest-first; tie-break on run_id for deterministic ordering when two
// runs share an exact started_at millisecond.
function compareByStartedAtDesc(a: RunRecord, b: RunRecord): number {
  if (a.started_at !== b.started_at) {
    return a.started_at < b.started_at ? 1 : -1;
  }
  return a.run_id < b.run_id ? 1 : -1;
}

function groupRunsByScenario(runs: RunRecord[]): Record<string, RunRecord[]> {
  const byScenario: Record<string, RunRecord[]> = {};
  for (const run of runs) {
    (byScenario[run.scenario] ??= []).push(run);
  }
  for (const list of Object.values(byScenario)) {
    list.sort(compareByStartedAtDesc);
  }
  return byScenario;
}

// Short clock time for the card row — full ISO is too wide for the card.
// Falls back to the raw string if Date parsing fails (shouldn't, but defence).
function formatStartedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function LogGenerator() {
  const { token, logout } = useAuth();
  const [scenarios, setScenarios] = useState<ScenarioSpec[]>([]);
  const [env, setEnv] = useState<AgitatorEnv | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [paramsByScenario, setParamsByScenario] = useState<Record<string, ParamState>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([listScenarios(token), getAgitatorEnv(token)])
      .then(([specs, envOut]) => {
        setScenarios(specs);
        setEnv(envOut);
        setParamsByScenario(
          specs.reduce<Record<string, ParamState>>((acc, s) => {
            acc[s.name] = buildDefaultParams(s);
            return acc;
          }, {}),
        );
      })
      .catch((err) => {
        if (err instanceof HttpError && err.status === 401) {
          logout();
          return;
        }
        setError("failed to load scenarios");
      });
  }, [token, logout]);

  const refreshRuns = useCallback(async () => {
    if (!token) return;
    try {
      const next = await listRuns(token);
      setRuns(next.runs);
    } catch (err) {
      if (err instanceof HttpError && err.status === 401) {
        logout();
      }
    }
  }, [token, logout]);

  const hasRunning = useMemo(() => runs.some((r) => r.state === "running"), [runs]);
  usePolling(refreshRuns, hasRunning ? ACTIVE_POLL_MS : IDLE_POLL_MS);

  const runsByScenario = useMemo(() => groupRunsByScenario(runs), [runs]);

  async function onRun(spec: ScenarioSpec) {
    if (!token) return;
    setError(null);
    try {
      await startRun(token, {
        scenario: spec.name,
        params: paramsByScenario[spec.name] ?? buildDefaultParams(spec),
      });
      await refreshRuns();
    } catch (err) {
      if (err instanceof HttpError) {
        setError(err.detail);
      } else {
        setError("failed to start run");
      }
    }
  }

  async function onCancel(runId: string) {
    if (!token) return;
    try {
      await cancelRun(token, runId);
      await refreshRuns();
    } catch (err) {
      if (err instanceof HttpError) {
        setError(err.detail);
      }
    }
  }

  function updateParam(scenarioName: string, paramName: string, value: number) {
    setParamsByScenario((prev) => ({
      ...prev,
      [scenarioName]: { ...(prev[scenarioName] ?? {}), [paramName]: value },
    }));
  }

  return (
    <section aria-labelledby="log-generator-heading">
      <div className="flex items-baseline justify-between">
        <h2 id="log-generator-heading" className="text-lg font-semibold text-slate-900">
          Log Generator
        </h2>
        {env && !env.enable_chaos && (
          <span
            className="text-xs text-slate-500"
            title="Set ENABLE_CHAOS=true in .env to enable the sda-degraded scenario."
            data-testid="chaos-disabled-note"
          >
            ENABLE_CHAOS is off — chaos-only scenarios are disabled
          </span>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-md bg-red-50 p-2 text-xs text-red-700"
          data-testid="error-banner"
        >
          {error}
        </p>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3" data-testid="scenario-grid">
        {scenarios.map((spec) => {
          const disabled = spec.requires_chaos && !(env?.enable_chaos ?? false);
          const scenarioRuns = runsByScenario[spec.name] ?? [];
          return (
            <article
              key={spec.name}
              className="flex min-h-[320px] flex-col rounded-md border border-slate-200 bg-white p-4 shadow-sm"
              data-testid={`scenario-card-${spec.name}`}
            >
              <header className="flex items-baseline justify-between">
                <h3 className="text-sm font-semibold text-slate-900">{spec.display_name}</h3>
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {spec.target_app}
                </span>
              </header>
              <p className="mt-2 text-xs text-slate-600">{spec.description}</p>

              <dl className="mt-3 space-y-2">
                {spec.params.map((p) => (
                  <div key={p.name} className="flex items-center justify-between gap-2 text-xs">
                    <dt className="text-slate-500">{p.name}</dt>
                    <dd>
                      <input
                        type="number"
                        aria-label={`${spec.name} ${p.name}`}
                        min={p.minimum}
                        max={p.maximum}
                        value={paramsByScenario[spec.name]?.[p.name] ?? p.default}
                        onChange={(e) =>
                          updateParam(spec.name, p.name, Number(e.target.value) || p.default)
                        }
                        className="w-24 rounded border border-slate-300 px-2 py-0.5 text-right"
                      />
                    </dd>
                  </div>
                ))}
              </dl>

              <button
                type="button"
                disabled={disabled}
                onClick={() => onRun(spec)}
                className="mt-3 w-full rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                data-testid={`run-button-${spec.name}`}
              >
                {disabled ? "Requires ENABLE_CHAOS=true" : "Run"}
              </button>

              {/* Inline per-scenario run history. `mt-auto` pushes this block
                  to the card foot so cards with different param counts still
                  line up the recent-runs strip vertically. */}
              <div className="mt-auto pt-3" data-testid={`scenario-runs-${spec.name}`}>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Recent runs
                </div>
                {scenarioRuns.length === 0 ? (
                  <p className="text-[11px] italic text-slate-400">No runs yet.</p>
                ) : (
                  <ul className="space-y-1">
                    {scenarioRuns.slice(0, PER_CARD_RUN_LIMIT).map((run) => (
                      <li
                        key={run.run_id}
                        className="flex items-center justify-between gap-2 text-[11px]"
                        data-testid={`run-row-${run.run_id}`}
                      >
                        <div className="flex min-w-0 items-center gap-1.5">
                          <RunStateBadge state={run.state} />
                          <span className="font-mono text-slate-500" title={run.started_at}>
                            {formatStartedAt(run.started_at)}
                          </span>
                          <span className="truncate text-slate-600">
                            {run.sent}/{run.succeeded}/{run.failed}
                          </span>
                        </div>
                        {run.state === "running" && (
                          <button
                            type="button"
                            onClick={() => onCancel(run.run_id)}
                            className="rounded border border-slate-300 px-1.5 py-0.5 text-slate-700 hover:bg-slate-100"
                            data-testid={`cancel-button-${run.run_id}`}
                          >
                            Cancel
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function RunStateBadge({ state }: { state: RunRecord["state"] }) {
  const className = [
    "rounded px-1.5 py-0.5 font-medium",
    state === "running" && "bg-amber-100 text-amber-800",
    state === "succeeded" && "bg-green-100 text-green-800",
    state === "failed" && "bg-red-100 text-red-800",
    state === "cancelled" && "bg-slate-200 text-slate-700",
  ]
    .filter(Boolean)
    .join(" ");
  return <span className={className}>{state}</span>;
}
