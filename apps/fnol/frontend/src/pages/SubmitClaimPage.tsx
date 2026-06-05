import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { HttpError, submitClaim } from "../lib/api";
import { useAuth } from "../lib/auth";

export function SubmitClaimPage() {
  const { token, claims, logout } = useAuth();
  const navigate = useNavigate();
  const [policyNumber, setPolicyNumber] = useState("");
  const [vin, setVin] = useState("");
  const [incidentAt, setIncidentAt] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token || !claims) {
      setError("session expired");
      return;
    }
    setSubmitting(true);
    try {
      const created = await submitClaim(
        {
          customer_id: claims.user_id,
          policy_number: policyNumber,
          vin,
          incident_at: new Date(incidentAt).toISOString(),
          description: description || undefined,
        },
        token,
      );
      navigate(`/claims/${created.id}`);
    } catch (err) {
      const msg = err instanceof HttpError ? err.detail : "submission failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-6 sm:py-10">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">File a Claim</h1>
          {claims && (
            <p className="mt-1 text-sm text-slate-600">
              Signed in as <span className="font-medium">{claims.user_id}</span>
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={logout}
          className="text-sm text-slate-600 underline-offset-2 hover:underline"
        >
          Sign out
        </button>
      </header>

      <form
        onSubmit={onSubmit}
        className="space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"
        aria-label="submit-claim"
      >
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Policy number</span>
          <input
            type="text"
            required
            placeholder="POL-1004"
            value={policyNumber}
            onChange={(e) => setPolicyNumber(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-base focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-slate-700">VIN</span>
          <input
            type="text"
            required
            value={vin}
            onChange={(e) => setVin(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-base font-mono uppercase focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-slate-700">Incident date/time</span>
          <input
            type="datetime-local"
            required
            value={incidentAt}
            onChange={(e) => setIncidentAt(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-base focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-slate-700">What happened?</span>
          <textarea
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-base focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
            placeholder="Brief description of the incident"
          />
        </label>

        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-slate-900 px-4 py-2.5 text-white font-medium hover:bg-slate-800 disabled:opacity-60"
        >
          {submitting ? "Submitting…" : "Submit claim"}
        </button>
      </form>
    </main>
  );
}
