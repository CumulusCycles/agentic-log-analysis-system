// Phase 7e (PR 4b) — Error Detail types.
// Mirror the FastAPI shapes in `dashboard/src/log_dashboard/schemas.py`
// (AgentAnalysis + ErrorDetailResponse).

import type { Citation } from "./chat";
import type { LogEntry } from "./logs";

export interface AgentAnalysis {
  answer: string;
  citations: Citation[];
  dry_run: boolean;
  tool_budget_exhausted: boolean;
}

export interface ErrorDetailResponse {
  entry: LogEntry;
  analysis: AgentAnalysis;
}
