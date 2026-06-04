import type { AppStatusKind } from "../types/logs";

const PALETTE: Record<AppStatusKind, string> = {
  ok: "bg-emerald-100 text-emerald-800",
  degraded: "bg-amber-100 text-amber-800",
  error: "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: AppStatusKind }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${PALETTE[status]}`}
      data-testid="status-badge"
      data-status={status}
    >
      {status}
    </span>
  );
}
