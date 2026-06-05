// Hand-authored TS mirror of dashboard/src/log_dashboard/schemas.py
// (the PR 3 Agitator types). Update by hand when the backend changes.

export interface ScenarioParam {
  name: string;
  minimum: number;
  maximum: number;
  default: number;
}

export interface ScenarioSpec {
  name: string;
  display_name: string;
  description: string;
  target_app: string;
  requires_chaos: boolean;
  params: ScenarioParam[];
}

export interface AgitatorEnv {
  enable_chaos: boolean;
}

export type RunState = "running" | "succeeded" | "failed" | "cancelled";

export interface RunRecord {
  run_id: string;
  scenario: string;
  params: Record<string, number>;
  state: RunState;
  started_at: string;
  ended_at: string | null;
  sent: number;
  succeeded: number;
  failed: number;
  last_status_code: number | null;
  last_error: string | null;
}

export interface RunListResponse {
  runs: RunRecord[];
}

export interface RunCreateRequest {
  scenario: string;
  params?: Record<string, number>;
}
