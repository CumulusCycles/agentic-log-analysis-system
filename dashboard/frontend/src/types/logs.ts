// Hand-authored TS mirror of dashboard/src/log_dashboard/schemas.py and
// dashboard/src/log_dashboard/ingest/spec.py. Update by hand when the backend
// schemas change.

export type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR";

export type AppName = "shared-data-api" | "fnol" | "customer-portal" | "agent-portal";

export const APP_NAMES: readonly AppName[] = [
  "shared-data-api",
  "fnol",
  "customer-portal",
  "agent-portal",
] as const;

export const LOG_LEVELS: readonly LogLevel[] = ["DEBUG", "INFO", "WARN", "ERROR"] as const;

export interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  app: AppName;
  event: string;
  fields: Record<string, unknown>;
  raw: string;
}

export interface LogsResponse {
  entries: LogEntry[];
  next_before: string | null;
}

export interface LevelCounts {
  info: number;
  warn: number;
  error: number;
}

export type AppStatusKind = "ok" | "degraded" | "error";

export interface AppStatus {
  name: AppName;
  status: AppStatusKind;
  file_present: boolean;
  last_seen_at: string | null;
  counts_1h: LevelCounts;
  counts_24h: LevelCounts;
  counts_7d: LevelCounts;
}

export interface StatusResponse {
  as_of: string;
  apps: AppStatus[];
  corpus_empty?: boolean;
  // Phase 7e (PR 4c): proactive scan findings + loop metadata. Older
  // backends won't ship these, so all four are optional on the wire.
  proactive_findings?: import("./proactive").ProactiveFinding[];
  scan_enabled?: boolean;
  last_scan_at?: string | null;
  next_scan_at?: string | null;
}

export type TimeWindow = "1h" | "24h" | "7d";

export interface LogsFilters {
  apps: AppName[];
  levels: LogLevel[];
  since: string | null;
  before: string | null;
  limit: number;
}

// Phase 7d — POST /api/logs/search
export interface LogsSearchRequest {
  query: string;
  apps?: AppName[];
  levels?: LogLevel[];
  since?: string | null;
  before?: string | null;
  top_k?: number;
}

export interface LogsSearchResponse {
  entries: LogEntry[];
  scores: number[];
}
