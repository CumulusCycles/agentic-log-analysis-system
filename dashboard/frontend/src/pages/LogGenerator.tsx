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

interface ParamState {
  [paramName: string]: number;
}

function buildDefaultParams(spec: ScenarioSpec): ParamState {
  return spec.params.reduce<ParamState>((acc, p) => {
    acc[p.name] = p.default;
    return acc;
  }, {});
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
          return (
            <article
              key={spec.name}
              className="rounded-md border border-slate-200 bg-white p-4 shadow-sm"
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
            </article>
          );
        })}
      </div>

      <h3 className="mt-8 text-sm font-semibold text-slate-900">Recent runs</h3>
      <ul className="mt-2 space-y-2" data-testid="recent-runs">
        {runs.length === 0 && <li className="text-xs text-slate-500">No runs yet.</li>}
        {runs
          .slice(-10)
          .reverse()
          .map((run) => (
            <li
              key={run.run_id}
              className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2 text-xs"
              data-testid={`run-row-${run.run_id}`}
            >
              <div className="flex items-center gap-3">
                <span
                  className={[
                    "rounded px-2 py-0.5 font-medium",
                    run.state === "running" && "bg-amber-100 text-amber-800",
                    run.state === "succeeded" && "bg-green-100 text-green-800",
                    run.state === "failed" && "bg-red-100 text-red-800",
                    run.state === "cancelled" && "bg-slate-200 text-slate-700",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  {run.state}
                </span>
                <span className="font-medium text-slate-900">{run.scenario}</span>
                <span className="text-slate-500">
                  sent {run.sent} · ok {run.succeeded} · fail {run.failed}
                </span>
                {run.last_status_code !== null && (
                  <span className="text-slate-400">last {run.last_status_code}</span>
                )}
              </div>
              {run.state === "running" && (
                <button
                  type="button"
                  onClick={() => onCancel(run.run_id)}
                  className="rounded border border-slate-300 px-2 py-0.5 text-slate-700 hover:bg-slate-100"
                  data-testid={`cancel-button-${run.run_id}`}
                >
                  Cancel
                </button>
              )}
            </li>
          ))}
      </ul>
    </section>
  );
}
