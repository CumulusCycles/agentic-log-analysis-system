// Phase 7e (PR 4c) — Proactive scan types.
// Mirror the FastAPI shapes in `dashboard/src/log_dashboard/schemas.py`
// (ProactiveSeverity + ProactiveFinding).

import type { Citation } from "./chat";

export type ProactiveSeverity = "info" | "warn" | "error";

export interface ProactiveFinding {
  id: string;
  scan_started_at: string;
  scan_completed_at: string;
  summary: string;
  severity: ProactiveSeverity;
  citations: Citation[];
  dry_run: boolean;
}
