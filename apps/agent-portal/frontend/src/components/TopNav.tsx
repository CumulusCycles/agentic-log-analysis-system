import { NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function TopNav() {
  const { logout, claims } = useAuth();
  const navigate = useNavigate();

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
            Agent Portal
          </span>
          <nav className="flex items-center gap-1" aria-label="primary">
            <NavLink to="/claims" className={linkClass}>
              Claims
            </NavLink>
            <NavLink to="/profile" className={linkClass}>
              Profile
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {claims?.user_id && (
            <span className="hidden text-sm text-slate-500 sm:inline">
              {claims.user_id}
            </span>
          )}
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
