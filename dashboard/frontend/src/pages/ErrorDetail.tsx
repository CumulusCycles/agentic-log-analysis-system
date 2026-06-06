import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { LevelPill } from "../components/LevelPill";
import { getError, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Citation } from "../types/chat";
import type { ErrorDetailResponse } from "../types/errors";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: ErrorDetailResponse }
  | { kind: "error"; status: number; detail: string };

function formatTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function ErrorDetail() {
  const { id } = useParams<{ id: string }>();
  const { token, logout } = useAuth();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    if (!id || !token) return;
    setState({ kind: "loading" });
    getError(token, id)
      .then((data) => {
        if (cancelled) return;
        setState({ kind: "ok", data });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof HttpError && err.status === 401) {
          logout();
          return;
        }
        if (err instanceof HttpError) {
          setState({ kind: "error", status: err.status, detail: err.detail });
        } else {
          setState({ kind: "error", status: 0, detail: "request failed" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id, token, logout]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6">
      <nav className="text-sm">
        <Link to="/logs" className="text-slate-500 hover:text-slate-700">
          ← Back to Log Explorer
        </Link>
      </nav>

      {state.kind === "loading" && (
        <p className="text-sm text-slate-500" role="status">
          Loading error detail…
        </p>
      )}

      {state.kind === "error" && (
        <ErrorState status={state.status} detail={state.detail} entryId={id ?? ""} />
      )}

      {state.kind === "ok" && <DetailBody data={state.data} />}
    </div>
  );
}

function ErrorState({
  status,
  detail,
  entryId,
}: {
  status: number;
  detail: string;
  entryId: string;
}) {
  if (status === 404) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-700">
        <h1 className="text-lg font-semibold text-slate-900">Entry not found</h1>
        <p className="mt-2">
          Entry <code className="rounded bg-slate-100 px-1 font-mono">{entryId}</code> isn’t in the
          Chroma corpus. Only WARN and ERROR entries pass the ingest gate, so INFO/DEBUG rows from
          the Log Explorer don’t have an Error Detail view.
        </p>
        <Link
          to="/logs"
          className="mt-3 inline-block rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
        >
          Back to Log Explorer
        </Link>
      </div>
    );
  }
  if (status === 503) {
    return (
      <div
        role="alert"
        className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"
      >
        <h1 className="text-base font-semibold">Error detail unavailable</h1>
        <p className="mt-1">{detail}</p>
      </div>
    );
  }
  return (
    <div
      role="alert"
      className="rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-700"
    >
      {status > 0 ? `${status}: ${detail}` : detail}
    </div>
  );
}

function DetailBody({ data }: { data: ErrorDetailResponse }) {
  const { entry, analysis } = data;
  return (
    <>
      <header className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold text-slate-900">Error Detail</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <LevelPill level={entry.level} />
          <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-700">
            {entry.app}
          </span>
          <span className="font-mono text-xs">{entry.event}</span>
          <span className="text-xs text-slate-500">{formatTs(entry.timestamp)}</span>
        </div>
      </header>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-700">Raw log line</h2>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {entry.raw}
        </pre>
      </section>

      {Object.keys(entry.fields).length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-700">Fields</h2>
          <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {Object.entries(entry.fields).map(([key, val]) => (
              <div key={key} className="flex gap-2">
                <dt className="font-mono text-slate-500">{key}</dt>
                <dd className="font-mono break-all text-slate-800">
                  {typeof val === "string" ? val : JSON.stringify(val)}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <SuggestedFix analysis={analysis} />
    </>
  );
}

function SuggestedFix({ analysis }: { analysis: ErrorDetailResponse["analysis"] }) {
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-4"
      aria-labelledby="suggested-fix-heading"
    >
      <header className="flex items-center gap-2">
        <h2 id="suggested-fix-heading" className="text-sm font-semibold text-slate-700">
          Suggested Fix
        </h2>
        {analysis.dry_run && (
          <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            DRY RUN
          </span>
        )}
        {analysis.tool_budget_exhausted && (
          <span className="rounded-md bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800">
            tool budget exhausted
          </span>
        )}
      </header>
      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-900">{analysis.answer}</p>
      {analysis.citations.length > 0 && <CitationsList citations={analysis.citations} />}
    </section>
  );
}

function CitationsList({ citations }: { citations: Citation[] }) {
  return (
    <div className="mt-3 flex flex-col gap-1">
      <span className="text-xs font-medium text-slate-500">
        Related entries ({citations.length})
      </span>
      <ul className="flex flex-col gap-1">
        {citations.map((c) => (
          <li key={c.id}>
            <Link
              to={`/errors/${encodeURIComponent(c.id)}`}
              className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
              title={c.raw}
              data-testid="citation-link"
            >
              <span className="font-mono text-slate-500">{c.app}</span>
              <LevelPill level={c.level} />
              <span className="font-mono">{c.event}</span>
              <span className="ml-auto text-[10px] text-slate-400">score {c.score.toFixed(3)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
