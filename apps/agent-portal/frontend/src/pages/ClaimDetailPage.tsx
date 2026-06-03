import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { StatusBadge } from "../components/StatusBadge";
import { StatusTimeline } from "../components/StatusTimeline";
import { TopNav } from "../components/TopNav";
import { getClaim, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { ClaimDetail } from "../types/api";

export function ClaimDetailPage() {
  const { token } = useAuth();
  const { id } = useParams<{ id: string }>();
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token || !id) return;
    let cancelled = false;
    setLoading(true);
    getClaim(token, id)
      .then((c) => {
        if (!cancelled) setClaim(c);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof HttpError ? err.detail : "failed to load claim",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, id]);

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-3xl px-4 py-6 sm:py-10">
        <Link
          to="/claims"
          className="inline-flex items-center text-sm text-slate-600 hover:text-slate-900"
        >
          ← All claims
        </Link>

        {loading && <p className="mt-6 text-slate-600">Loading…</p>}

        {error && (
          <p role="alert" className="mt-6 text-sm text-red-700">
            {error}
          </p>
        )}

        {claim && (
          <>
            <article className="mt-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
              <header className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Claim
                  </p>
                  <h1 className="font-mono text-base font-semibold">
                    {claim.id}
                  </h1>
                </div>
                <StatusBadge status={claim.current_status} />
              </header>

              <dl className="mt-6 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-slate-500">Policy</dt>
                  <dd className="font-mono text-slate-900">
                    {claim.policy_number}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Customer</dt>
                  <dd className="font-mono text-xs text-slate-700">
                    {claim.customer_id}
                  </dd>
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
                  <dt className="text-slate-500">VIN</dt>
                  <dd className="font-mono text-xs text-slate-700">
                    {claim.vin}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Incident</dt>
                  <dd className="text-slate-900">
                    {new Date(claim.incident_at).toLocaleString()}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Assigned adjuster</dt>
                  <dd className="font-mono text-xs text-slate-700">
                    {claim.assigned_adjuster_id ?? "—"}
                  </dd>
                </div>
              </dl>

              {claim.description && (
                <p className="mt-6 border-t border-slate-100 pt-4 text-sm text-slate-700">
                  {claim.description}
                </p>
              )}
            </article>

            <section className="mt-6">
              <h2 className="text-lg font-semibold tracking-tight">
                Status history
              </h2>
              <div className="mt-3">
                <StatusTimeline history={claim.history} />
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
