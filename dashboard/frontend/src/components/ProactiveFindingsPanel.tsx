import { Link } from "react-router-dom";

import type { ProactiveFinding, ProactiveSeverity } from "../types/proactive";

// Inline panel on the Overview page that surfaces the most recent proactive
// scan findings. Renders nothing when scan is disabled AND there are no
// findings — keeps the page clean for operators who haven't opted in.
//
// The opt-in chain (DASHBOARD_PROACTIVE_SCAN_ENABLED + LLM_DRY_RUN=false) is
// documented in ADR-016. This component just consumes the boolean and the
// finding list — it doesn't know about the env knobs.

interface Props {
  findings: ProactiveFinding[];
  scanEnabled: boolean;
  lastScanAt: string | null;
}

const SEVERITY_STYLES: Record<ProactiveSeverity, string> = {
  error: "bg-red-100 text-red-800",
  warn: "bg-amber-100 text-amber-800",
  info: "bg-slate-100 text-slate-700",
};

export function ProactiveFindingsPanel({ findings, scanEnabled, lastScanAt }: Props) {
  if (!scanEnabled && findings.length === 0) {
    return null;
  }

  return (
    <section
      aria-labelledby="proactive-findings-heading"
      className="mt-3 rounded-md border border-slate-200 bg-white p-3"
      data-testid="proactive-findings-panel"
    >
      <div className="flex items-baseline justify-between">
        <h3 id="proactive-findings-heading" className="text-sm font-semibold text-slate-900">
          Proactive findings
        </h3>
        {lastScanAt && (
          <span className="text-xs text-slate-500" data-testid="last-scan-at">
            last scan {new Date(lastScanAt).toLocaleString()}
          </span>
        )}
      </div>

      {findings.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500" data-testid="proactive-findings-empty">
          No anomalies detected in the most recent scan.
        </p>
      ) : (
        <ol className="mt-2 space-y-2" data-testid="proactive-findings-list">
          {findings.map((finding) => (
            <li
              key={finding.id}
              className="rounded-md bg-slate-50 px-3 py-2"
              data-testid="proactive-finding"
            >
              <div className="flex items-baseline gap-2">
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${SEVERITY_STYLES[finding.severity]}`}
                  data-testid="severity-pill"
                >
                  {finding.severity}
                </span>
                <span className="text-xs text-slate-500">
                  {new Date(finding.scan_completed_at).toLocaleString()}
                </span>
                {finding.dry_run && <span className="text-xs text-slate-400">(dry-run)</span>}
              </div>
              <p className="mt-1 text-sm text-slate-800">{finding.summary}</p>
              {finding.citations.length > 0 && (
                <ul className="mt-1 space-y-0.5" data-testid="proactive-finding-citations">
                  {finding.citations.map((cite) => (
                    <li key={cite.id} className="text-xs">
                      <Link
                        to={`/errors/${cite.id}`}
                        className="text-sky-700 hover:underline"
                        data-testid="proactive-citation-link"
                      >
                        {cite.app} · {cite.event}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
