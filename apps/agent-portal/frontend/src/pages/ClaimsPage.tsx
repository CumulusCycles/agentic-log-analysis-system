import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

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
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-10">
        <h1 className="text-2xl font-semibold tracking-tight">All Claims</h1>
        <p className="mt-1 text-sm text-slate-600">
          Click a claim to view detail and status history.
        </p>

        {loading && <p className="mt-4 text-slate-600">Loading…</p>}

        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {error}
          </p>
        )}

        {claims && claims.length === 0 && (
          <p className="mt-4 text-slate-600">No claims in the system.</p>
        )}

        {claims && claims.length > 0 && (
          <ul className="mt-6 space-y-3" data-testid="claims-list">
            {claims.map((claim) => (
              <li key={claim.id}>
                <Link
                  to={`/claims/${claim.id}`}
                  className="block rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 hover:ring-slate-400"
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

                  <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                    <div>
                      <dt className="text-slate-500">Policy</dt>
                      <dd className="font-mono text-slate-900">{claim.policy_number}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Customer</dt>
                      <dd className="font-mono text-xs text-slate-700">{claim.customer_id}</dd>
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
                        {new Date(claim.incident_at).toLocaleDateString()}
                      </dd>
                    </div>
                  </dl>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
