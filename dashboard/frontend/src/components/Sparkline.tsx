import { Area, AreaChart, ResponsiveContainer } from "recharts";

import type { StatusHistoryBucket } from "../types/logs";

const SPARKLINE_HEIGHT_PX = 56;

// Colours match the existing badge palette used elsewhere in the dashboard:
// info=slate-300, warn=amber-500, error=rose-500. The stacked order is
// info (bottom) → warn (middle) → error (top) so a quiet app shows a slim
// grey baseline and errors are visually loudest at the top of the band.
const COLOR_INFO = "#cbd5e1"; // slate-300
const COLOR_WARN = "#f59e0b"; // amber-500
const COLOR_ERROR = "#f43f5e"; // rose-500

interface SparklineProps {
  buckets: StatusHistoryBucket[];
}

/**
 * Compact ~60px stacked area chart of per-bucket info/warn/error counts for
 * one app. No axes, no tooltip — the surrounding StatusCard already shows
 * totals and the card is itself a navigation link, so the sparkline stays
 * non-interactive. When `buckets` is empty (or all-zero) the chart still
 * renders so the layout doesn't jump.
 */
export function Sparkline({ buckets }: SparklineProps) {
  // `buckets` is keyed by bucket-start; recharts wants whatever the data
  // array looks like + dataKeys that point at numeric properties. We hand
  // it the buckets directly — `ts` is unused (no axis), info/warn/error
  // map to the three series.
  return (
    <div
      data-testid="sparkline"
      style={{ height: SPARKLINE_HEIGHT_PX }}
      className="w-full"
      aria-hidden="true"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={buckets} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
          <Area
            type="monotone"
            dataKey="info"
            stackId="counts"
            stroke={COLOR_INFO}
            fill={COLOR_INFO}
            fillOpacity={0.45}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="warn"
            stackId="counts"
            stroke={COLOR_WARN}
            fill={COLOR_WARN}
            fillOpacity={0.65}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="error"
            stackId="counts"
            stroke={COLOR_ERROR}
            fill={COLOR_ERROR}
            fillOpacity={0.85}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
