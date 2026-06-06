// Simple horizontal-bar chart using Tailwind. No charting library.
// Each row: label on the left, a flexed bar in the middle, count on the right.
// Bar widths are computed as a percentage of the max value in the dataset so
// the visual is self-scaling regardless of absolute magnitude.

export interface BarChartDatum {
  label: string;
  value: number;
}

export interface BarChartProps {
  data: BarChartDatum[];
  accent?: "blue" | "amber" | "rose" | "emerald" | "slate";
  ariaLabel?: string;
  emptyHint?: string;
}

const ACCENT_CLASSES: Record<NonNullable<BarChartProps["accent"]>, string> = {
  blue: "bg-blue-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
  emerald: "bg-emerald-500",
  slate: "bg-slate-400",
};

export function BarChart({
  data,
  accent = "blue",
  ariaLabel,
  emptyHint = "No data.",
}: BarChartProps) {
  if (data.length === 0) {
    return <p className="text-sm text-slate-500">{emptyHint}</p>;
  }
  const max = data.reduce((acc, d) => (d.value > acc ? d.value : acc), 0);
  const accentClass = ACCENT_CLASSES[accent];

  return (
    <ul className="space-y-1" role="list" aria-label={ariaLabel} data-testid="bar-chart">
      {data.map((d) => {
        // Guard the percentage math — max=0 (all values zero) would NaN
        // without this. We still render the row so the operator sees the
        // label/value pair, just with a 0-width bar.
        const pct = max === 0 ? 0 : Math.max(2, (d.value / max) * 100);
        const isZero = d.value === 0;
        return (
          <li key={d.label} className="flex items-center gap-2 text-xs">
            <span className="w-32 shrink-0 truncate text-right text-slate-600" title={d.label}>
              {d.label}
            </span>
            <span className="flex-1 rounded bg-slate-100">
              <span
                className={`block h-4 rounded ${accentClass}`}
                style={{ width: isZero ? "0%" : `${pct}%` }}
                data-testid="bar-chart-bar"
                aria-hidden="true"
              />
            </span>
            <span className="w-12 shrink-0 text-right font-mono text-slate-700">
              {d.value.toLocaleString()}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
