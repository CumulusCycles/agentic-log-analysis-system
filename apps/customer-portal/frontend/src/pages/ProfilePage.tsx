import { useEffect, useState } from "react";

import { TopNav } from "../components/TopNav";
import { getProfile, HttpError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { UserOut } from "../types/api";

export function ProfilePage() {
  const { token } = useAuth();
  const [profile, setProfile] = useState<UserOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    getProfile(token)
      .then((p) => {
        if (!cancelled) setProfile(p);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof HttpError ? err.detail : "failed to load profile",
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
      <main className="mx-auto max-w-2xl px-4 py-6 sm:py-10">
        <h1 className="text-2xl font-semibold tracking-tight">My Profile</h1>

        {loading && <p className="mt-4 text-slate-600">Loading…</p>}

        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {error}
          </p>
        )}

        {profile && (
          <article className="mt-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <dl className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="font-medium text-slate-500">Name</dt>
                <dd className="mt-0.5 text-slate-900">
                  {profile.display_name}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-500">Username</dt>
                <dd className="mt-0.5 text-slate-900">{profile.username}</dd>
              </div>
              <div>
                <dt className="font-medium text-slate-500">Role</dt>
                <dd className="mt-0.5 text-slate-900">{profile.role}</dd>
              </div>
              <div>
                <dt className="font-medium text-slate-500">User ID</dt>
                <dd className="mt-0.5 font-mono text-xs text-slate-700">
                  {profile.id}
                </dd>
              </div>
            </dl>
          </article>
        )}
      </main>
    </div>
  );
}
