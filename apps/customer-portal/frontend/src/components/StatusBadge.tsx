const PALETTE: Record<string, string> = {
  submitted: "bg-slate-100 text-slate-700",
  triaged: "bg-blue-100 text-blue-700",
  investigating: "bg-amber-100 text-amber-800",
  settled: "bg-emerald-100 text-emerald-800",
  closed: "bg-slate-200 text-slate-700",
  denied: "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = PALETTE[status] ?? "bg-slate-100 text-slate-700";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
      data-testid="status-badge"
    >
      {status}
    </span>
  );
}
