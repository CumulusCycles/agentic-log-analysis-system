import { NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function TopNav() {
  const { claims, logout } = useAuth();
  const navigate = useNavigate();
  const username = claims?.sub ?? "admin";

  function onLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  const linkClass = ({ isActive }: { isActive: boolean }): string =>
    [
      "rounded-md px-3 py-1.5 text-sm font-medium",
      isActive
        ? "bg-slate-900 text-white"
        : "text-slate-700 hover:bg-slate-200",
    ].join(" ");

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-6">
          <span className="text-base font-semibold tracking-tight">
            Agentic Log Analysis Dashboard
          </span>
          <nav className="flex items-center gap-1" aria-label="primary">
            <NavLink to="/" end className={linkClass}>
              Overview
            </NavLink>
            <NavLink to="/logs" className={linkClass}>
              Log Explorer
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-slate-500 sm:inline">
            Signed in as <span className="font-medium">{username}</span>
          </span>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-100"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
