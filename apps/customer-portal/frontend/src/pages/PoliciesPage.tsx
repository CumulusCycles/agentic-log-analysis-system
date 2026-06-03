import { useEffect, useState } from "react";

import { TopNav } from "../components/TopNav";
import { getPolicies, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { PolicyOut } from "../types/api";

function formatPremium(cents: number): string {
  return `$${(cents / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}/yr`;
}

export function PoliciesPage() {
  const { token } = useAuth();
  const [policies, setPolicies] = useState<PolicyOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    getPolicies(token)
      .then((p) => {
        if (!cancelled) setPolicies(p);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof HttpError ? err.detail : "failed to load policies",
        );
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
        <h1 className="text-2xl font-semibold tracking-tight">My Policies</h1>

        {loading && <p className="mt-4 text-slate-600">Loading…</p>}

        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {error}
          </p>
        )}

        {policies && policies.length === 0 && (
          <p className="mt-4 text-slate-600">No policies on file.</p>
        )}

        {policies && policies.length > 0 && (
          <ul className="mt-6 grid gap-4 sm:grid-cols-2">
            {policies.map((policy) => (
              <li
                key={policy.policy_number}
                className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200"
              >
                <header className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                      Policy
                    </p>
                    <h2 className="font-mono text-lg font-semibold">
                      {policy.policy_number}
                    </h2>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                    {policy.coverage_type}
                  </span>
                </header>

                <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-slate-500">Effective</dt>
                    <dd className="text-slate-900">{policy.effective_date}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Expires</dt>
                    <dd className="text-slate-900">{policy.expiration_date}</dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="text-slate-500">Premium</dt>
                    <dd className="text-slate-900">
                      {formatPremium(policy.premium_cents)}
                    </dd>
                  </div>
                </dl>

                <section className="mt-4 border-t border-slate-100 pt-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Vehicles
                  </p>
                  <ul className="mt-2 space-y-1 text-sm">
                    {policy.vehicles.map((v) => (
                      <li
                        key={v.vin}
                        className="flex items-baseline justify-between gap-2"
                      >
                        <span className="text-slate-900">
                          {v.year} {v.make} {v.model}
                        </span>
                        <span className="font-mono text-xs text-slate-500">
                          {v.vin}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
