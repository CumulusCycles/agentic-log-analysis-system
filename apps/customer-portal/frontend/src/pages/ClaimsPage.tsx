import { useEffect, useState } from "react";

import { StatusBadge } from "../components/StatusBadge";
import { TopNav } from "../components/TopNav";
import { getClaims, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { ClaimOut } from "../types/api";

export function ClaimsPage() {
  const { token } = useAuth();
  const [claims, setClaims] = useState<ClaimOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    getClaims(token)
      .then((c) => {
        if (!cancelled) setClaims(c);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof HttpError ? err.detail : "failed to load claims");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-5xl px-4 py-6 sm:py-10">
        <h1 className="text-2xl font-semibold tracking-tight">My Claims</h1>

        {loading && <p className="mt-4 text-slate-600">Loading…</p>}

        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {error}
          </p>
        )}

        {claims && claims.length === 0 && <p className="mt-4 text-slate-600">No claims filed.</p>}

        {claims && claims.length > 0 && (
          <ul className="mt-6 space-y-3">
            {claims.map((claim) => (
              <li
                key={claim.id}
                className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200"
              >
                <header className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                      Claim
                    </p>
                    <h2 className="font-mono text-sm font-semibold">{claim.id}</h2>
                  </div>
                  <StatusBadge status={claim.current_status} />
                </header>

                <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-slate-500">Policy</dt>
                    <dd className="font-mono text-slate-900">{claim.policy_number}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Vehicle</dt>
                    <dd className="text-slate-900">
                      {claim.vehicle_snapshot
                        ? `${claim.vehicle_snapshot.year} ${claim.vehicle_snapshot.make} ${claim.vehicle_snapshot.model}`
                        : claim.vin}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Incident</dt>
                    <dd className="text-slate-900">
                      {new Date(claim.incident_at).toLocaleString()}
                    </dd>
                  </div>
                </dl>

                {claim.description && (
                  <p className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-700">
                    {claim.description}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
