// Phase 7e (PR 4a) — AI Chat types.
// Mirror the FastAPI shapes in `dashboard/src/log_dashboard/schemas.py`.

import type { LogLevel } from "./logs";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface Citation {
  id: string;
  timestamp: string;
  level: LogLevel;
  app: string;
  event: string;
  raw: string;
  score: number;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  streaming?: boolean;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  session_id: string;
  dry_run: boolean;
  tool_budget_exhausted: boolean;
}
