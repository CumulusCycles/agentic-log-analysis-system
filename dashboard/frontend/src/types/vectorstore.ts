// Types for /api/chroma/stats — must mirror dashboard/src/log_dashboard/schemas.py
// (ChromaStatsResponse / DayCount / EventCount).

export interface DayCount {
  date: string; // "YYYY-MM-DD"
  count: number;
}

export interface EventCount {
  event: string;
  count: number;
}

export interface ChromaStatsResponse {
  total_count: number;
  by_app: Record<string, number>;
  by_level: Record<string, number>;
  by_source: Record<string, number>;
  by_event: EventCount[]; // top 10, descending
  by_day: DayCount[]; // last 30 days, ascending
  embedding_model: string;
  dimensions: number;
  as_of: string; // ISO timestamp
}
