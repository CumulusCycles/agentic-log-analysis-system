import type { LogLevel } from "../types/logs";

const PALETTE: Record<LogLevel, string> = {
  DEBUG: "bg-slate-100 text-slate-600",
  INFO: "bg-blue-100 text-blue-700",
  WARN: "bg-amber-100 text-amber-800",
  ERROR: "bg-red-100 text-red-700",
};

export function LevelPill({ level }: { level: LogLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${PALETTE[level]}`}
      data-testid="level-pill"
      data-level={level}
    >
      {level}
    </span>
  );
}
