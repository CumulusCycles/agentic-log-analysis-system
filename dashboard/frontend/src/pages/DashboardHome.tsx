import { useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function DashboardHome() {
  const { claims, logout } = useAuth();
  const navigate = useNavigate();
  const username = claims?.sub ?? "admin";

  function onLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight">
            Agentic Log Analysis Dashboard
          </h1>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">
              Signed in as <span className="font-medium">{username}</span>
            </span>
            <button
              type="button"
              onClick={onLogout}
              className="rounded-md border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">
        <section
          className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"
          aria-labelledby="scaffold-heading"
        >
          <h2
            id="scaffold-heading"
            className="text-base font-semibold text-slate-900"
          >
            Scaffold ready
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Phase 7a is the scaffold + standalone auth slice. Log ingestion
            (Phase 7b) and the Overview + Log Explorer screens (Phase 7c) are
            the next planned PRs.
          </p>
        </section>
      </main>
    </div>
  );
}
