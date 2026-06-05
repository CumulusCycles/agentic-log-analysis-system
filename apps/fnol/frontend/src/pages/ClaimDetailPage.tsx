import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getClaim, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { ClaimDetail } from "../types/api";

export function ClaimDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id || !token) return;
    let cancelled = false;
    setLoading(true);
    getClaim(id, token)
      .then((c) => {
        if (!cancelled) setClaim(c);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof HttpError ? err.detail : "failed to load claim");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, token]);

  return (
    <main className="mx-auto max-w-md px-4 py-6 sm:py-10">
      <Link
        to="/submit"
        className="mb-4 inline-block text-sm text-slate-600 underline-offset-2 hover:underline"
      >
        ← File another claim
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">Claim {id}</h1>

      {loading && <p className="mt-4 text-slate-600">Loading…</p>}

      {error && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      )}

      {claim && (
        <article className="mt-4 space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-medium text-slate-500">Status</dt>
              <dd className="mt-0.5 text-slate-900">{claim.current_status}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Policy</dt>
              <dd className="mt-0.5 text-slate-900">{claim.policy_number}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">VIN</dt>
              <dd className="mt-0.5 font-mono text-slate-900">{claim.vin}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Filed</dt>
              <dd className="mt-0.5 text-slate-900">
                {new Date(claim.created_at).toLocaleString()}
              </dd>
            </div>
          </dl>
          {claim.description && (
            <p className="border-t border-slate-100 pt-4 text-slate-700">{claim.description}</p>
          )}

          <section className="border-t border-slate-100 pt-4">
            <h2 className="text-sm font-medium text-slate-500">History</h2>
            <ol className="mt-2 space-y-1 text-sm">
              {claim.history.map((entry, idx) => (
                <li key={idx} className="flex justify-between gap-3 text-slate-700">
                  <span>
                    {entry.from_status ?? "—"} → <strong>{entry.to_status}</strong>
                  </span>
                  <span className="text-slate-500">
                    {new Date(entry.changed_at).toLocaleString()}
                  </span>
                </li>
              ))}
              {claim.history.length === 0 && (
                <li className="text-slate-500">No status changes yet.</li>
              )}
            </ol>
          </section>
        </article>
      )}
    </main>
  );
}
