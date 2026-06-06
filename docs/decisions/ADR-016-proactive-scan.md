# ADR-016: Proactive Background Scan (Phase 7e PR 4c)

**Status:** Accepted

**Closes Phase 7.** Final slice of the 7e LangGraph work.

## Decisions

1. **A background asyncio task wakes every `DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS` (default 900 = 15 min)** and asks the SAME compiled LangGraph agent that backs `/api/chat` to scan the last `DASHBOARD_PROACTIVE_SCAN_LOOKBACK_MINUTES` (default 30) of logs for anomalies. Implemented in `dashboard/src/log_dashboard/agent/proactive.py`; wired into `main.py` lifespan with `asyncio.create_task` + `task.cancel()` on shutdown — same pattern the backfill task already uses.
2. **The loop is opt-in via `DASHBOARD_PROACTIVE_SCAN_ENABLED=false` default.** Operator flips to `true` in `.env` and restarts the dashboard. When false, no task is scheduled and `/api/status` reports `scan_enabled: false`.
3. **Real scans require BOTH `proactive_scan_enabled=True` AND `dashboard_llm_dry_run=False`.** Either alone is safe — dry-run wakes the loop on schedule, logs `proactive_scan_skipped reason=llm_dry_run`, and goes back to sleep without touching OpenAI. The cost-safety asymmetry from ADR-015 §5 extends to the background loop.
4. **The agent answers with a 1–2 sentence summary OR with the literal token `NO_ANOMALIES` when the scan is quiet.** Sentinel match in `proactive.py::_run_one_scan` short-circuits — no finding is stored. The buffer stays empty during steady-state and only grows when there's actually something to surface.
5. **Findings ride on `/api/status`, not a new endpoint.** `StatusResponse` gains `proactive_findings: ProactiveFinding[]` (top-N newest first, capped by `DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS=5`), `scan_enabled`, `last_scan_at`, `next_scan_at`. The existing 15s status poll on the Overview surfaces them inline above the status grid. No second endpoint, no second polling cadence.
6. **Findings live in a `collections.deque(maxlen=50)` ring buffer in process memory.** Restart-lossy by design — same posture as the Agitator's `RunRegistry`. The durable signal lives in Chroma + the log volumes; findings are just the agent's running commentary.
7. **Severity is derived deterministically from the citation set**, not from the LLM. Any cited entry at ERROR → `error`; else any at WARN → `warn`; else `info`. The agent's narrative can describe the anomaly however it wants, but the UI's pill color is grounded in the underlying log levels the citations point at.
8. **Identity:** `id` is `"proactive:{uuid4-hex}"` — opaque to the client; React list key only. Distinct shape from `LogEntry.id` (`{app}:{16 hex}`) so the `/errors/{id}` regex naturally rejects a finding id.

## Settings

```
DASHBOARD_PROACTIVE_SCAN_ENABLED             # bool, default false       — opt-in switch
DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS    # int,  default 900         — loop cadence (60..86400)
DASHBOARD_PROACTIVE_SCAN_LOOKBACK_MINUTES    # int,  default 30          — query window (5..1440)
DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS        # int,  default 5           — top-N on /api/status (1..20)
```

## Opt-in truth table

| `DRY_RUN` | `SCAN_ENABLED` | Behavior | Cost |
|---|---|---|---|
| true (default) | false (default) | No loop. Chat works (operator-driven, dry-run). | $0 |
| true | true | Loop wakes on schedule, logs `proactive_scan_skipped reason=llm_dry_run`, sleeps. Useful to verify scheduling. | $0 |
| false | false | No loop. Chat works (operator-driven, real OpenAI). | Per-chat-call |
| false | true | **Real scans.** ~96 scans/day at 15-min cadence. | See cost analysis |

## Cost analysis

One scan = one graph run = up to `LLM_MAX_TOOL_CALLS_PER_REQUEST=4` tool calls (each is a Chroma vector search, free) + at most two LLM calls (the `analyze` and `predict` nodes share `_invoke_llm_with_tools`). Cap order of magnitude per scan: ~4k input tokens × 2 calls + ~1k output tokens × 1 call. At gpt-4o list prices ($2.50/1M input, $10/1M output), that's roughly $0.03 per scan worst case. At 15-min cadence = 96 scans/day = ~$3/day worst case. The `NO_ANOMALIES` sentinel short-circuits the post-tool response message but the cost cap still bounds the upper limit.

Operators on a budget can either raise the interval (`DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS=3600` = $0.72/day) or keep the loop off.

## Why this shape

**Why deferred to PR 4c, not 4a.** PR 4a (#37) shipped the reactive surface (chat). The proactive surface is the second half of "agentic" — periodic checks the operator doesn't have to remember to run. Splitting it from 4a kept that PR scoped and let the LLM safety asymmetry (`DRY_RUN`) bake in before the loop's cost surface landed.

**Why skip on dry-run rather than run with a "dry-run" marker.** `_DryRunChatModel` returns the same canned answer every time. A dry-run scan would store an identical noise finding on every cycle, polluting the buffer + UI. Skipping is the cleanest answer; the schema retains a `dry_run` flag on each finding for a future policy flip.

**Why extend `/api/status` instead of `/api/proactive-findings`.** Findings are at most 5 inline cards on the Overview — small payload, same poll cadence as the rest of the page. A separate endpoint would add a parallel poll without any UX benefit. If a future PR adds a dedicated findings page with history + filters, that's the right time to split.

**Why the `NO_ANOMALIES` sentinel.** The agent needs a way to declare a scan quiet without generating a noise summary. A sentinel token in the prompt is cheap, deterministic, and round-trips through the dry-run model too (when we eventually want dry-run scans). The alternative — heuristics on summary text like "no" / "nothing" — is brittle.

**Why severity is deterministic (citation levels) instead of LLM-rated.** The agent already has an incentive to use dramatic language (the model was trained on incident postmortems). Coloring the pill from `extract_citations` ensures the visual signal matches what the operator would see if they clicked through to `/errors/:id`. The LLM picks WORDS; the citation levels pick COLORS.

**Why `jwt_sub: "system:proactive-scan"`.** LangSmith metadata filters by `jwt_sub`. Tagging proactive scans with a distinct subject makes them filterable in the LangSmith UI without conflating with real admin chat sessions.

**Why `findings_buffer` lives on `app.state` unconditionally.** The buffer is built even when the loop is off, so `/api/status` can always populate `proactive_findings: []` without state checks. The lifespan code path is cleaner — same shape regardless of opt-in.

**Why no graceful shutdown of in-flight scans.** A scan iteration is bounded by the cost caps (≤4 tool calls + ≤2 LLM calls). `task.cancel()` interrupts the `await graph.ainvoke(...)` cleanly. Worst case: one orphaned LangSmith trace per shutdown — acceptable.

## Bundled with this PR

**Chaos middleware level split (ADR-013 amendment).** The proactive scan is materially crippled with no ERROR-tier signal in Chroma — the hardened apps don't escalate 5xx to ERROR-level logs. Bundled fix: chaos middleware's `error:<5xx>` branch now logs at ERROR instead of WARN. 4xx and `slow:` paths stay WARN. Per `feedback_bundle_when_feature_value_is_tied`.

**New Agitator scenario `error-burst`.** Mirrors `sda-degraded` but sends `X-Chaos: error:500` instead of `X-Chaos: slow:500`, so operators can drive ERROR-tier signal into Chroma on demand. One file, requires `ENABLE_CHAOS=true` per the existing chaos-gating pattern.

## Consequences

- **`.env.example` gains 4 new keys** under a comment block that re-states the opt-in chain.
- **`StatusResponse` schema gains 4 fields** — all backwards-compatible defaults so older frontends keep working.
- **`/api/status` response payload grows** by at most `5 × (summary + citations)` bytes when findings exist. Empty case adds ~80 bytes of nulls + flags.
- **No new public route.** Findings deep-link via citations to the existing `GET /api/errors/{id}` route (PR 4b).
- **`dashboard.md` gains a "Proactive Scan (PR 4c ✅)" block** mirroring the existing "LangGraph Agent (PR 4a ✅)" structure.
- **Test surface:** ~17 new unit tests in `test_proactive_scan.py`, 2 new tests in `test_status_endpoint.py`, 2 new tests across `test_agitator_routes.py` + `test_agitator_scenarios.py`, 6 new frontend tests in `proactive-findings.test.tsx`, 1 new Playwright spec × 2 viewports, plus 2 new chaos tests per app × 4 apps.

## References

- ADR-013 — chaos middleware (amended 2026-06-06 for the level split)
- ADR-015 — Phase 7e LangGraph agent (PR 4a) + the cost-safety asymmetry this ADR extends
- `project_no_error_path_in_apps` memory — the WARN-only corpus problem this PR solves
- `feedback_bundle_when_feature_value_is_tied` memory — bundling rationale
- `feedback_no_paid_api_calls_without_confirmation` — DRY_RUN-default-on protects operators from surprise spend
