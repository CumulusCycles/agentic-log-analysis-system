# ADR-015 — LangGraph agent for the AI Chat slice (Phase 7e, PR 4a)

**Status**: Accepted
**Date**: 2026-06-05
**Supersedes**: none
**Related**: ADR-006 (standalone dashboard auth), ADR-011 (X-Source convention),
ADR-014 (Agitator bundled into the dashboard)

## Context

Phase 7e is the LLM slice that closes Phase 7. The dashboard's primary
deliverable — "an agentic AI system that monitors logs, identifies issues,
suggests remediation, and proactively predicts problems" — only ships
once this layer lands.

7d already wired:
- Chroma persistent collection populated by the ingest pipeline
- `OpenAIEmbeddings(text-embedding-3-small)` for embedding logs
- `/api/logs/search` semantic search over Chroma
- LangSmith env propagation (`configure_langsmith`)

PR 4a is the first of three Phase 7e sub-PRs:

- **PR 4a** (this ADR) — LangGraph StateGraph + `POST /api/chat` + AI Chat UI
- **PR 4b** — `GET /api/errors/{id}` + Error Detail UI (depends on the agent)
- **PR 4c** — Proactive background scan (every N minutes)

This ADR captures the design decisions baked into 4a.

## Decisions

### 1. 5-node `StateGraph` with names from `.claude/rules/dashboard.md:24`

```
START → ingest → analyze → (tool_calls? correlate → predict → analyze : respond) → END
```

| Node | Responsibility |
|---|---|
| `ingest` | Sanitise user input; reset per-request `tool_budget_remaining` from settings; pin `session_id` + `jwt_sub`; clear `citations`. No LLM call. |
| `analyze` | First LLM call. Model decides whether to call `query_logs` / `get_app_status` or answer directly. |
| `correlate` | Manual tool dispatch — executes each `tool_call` on the previous AIMessage and produces `ToolMessage`s. Decrements `tool_budget_remaining`. |
| `predict` | Post-tool LLM call. Reflects on tool output; may request more tools or finalise. |
| `respond` | Terminal node — harvests `CitedLogEntry` instances from the `ToolMessage` payloads and stashes them in `state["citations"]`. |

`analyze` and `predict` share the same `_invoke_llm_with_tools` body. They
are separate nodes so the rule's 5-name palette is satisfied verbatim and
PR 4c can plug different prompts / middleware into `predict` without
touching `analyze`.

### 2. Tools (DI'd at graph-build time, no globals)

- `query_logs(query, apps?, levels?, since_minutes?, top_k=10)` — wraps
  `langchain_chroma.Chroma.similarity_search_with_score` and returns a list
  of `CitedLogEntry` dicts. Hard cap `top_k=20`.
- `get_app_status(app=None)` — wraps `routers/status.py::compute_app_status`
  over a fresh `read_recent_entries` slice.

`build_tools(settings, vectorstore)` closes over both at graph build time.
`vectorstore=None` is permitted (degraded mode); `query_logs` returns
`{"results": [], "tool_error": "vectorstore_unavailable"}` and the graph
keeps running.

### 3. Manual tool dispatch instead of `langgraph.prebuilt.ToolNode`

`ToolNode` injects a runtime context from LangGraph's pregel runner that
is only present when the node runs inside a compiled graph. Unit tests
that call the wrapper directly trip `Missing required config key 'N/A'
for 'tools'`. Replacing it with ~20 lines of manual dispatch
(`{ tool.name: tool }`, iterate `tool_calls`, `asyncio.to_thread(tool.invoke,
args)`, build `ToolMessage`) sidesteps the runtime-injection coupling, has
no hidden state, and lets us decrement the per-request tool budget
atomically with the dispatch.

### 4. Session memory: `InMemorySaver` keyed by `thread_id="{jwt_sub}:{session_id}"`

Three options were considered:

| Option | Pro | Con | Decision |
|---|---|---|---|
| `InMemorySaver` (in-process) | Zero new infra; matches RunRegistry's "restart clears history" stance; aligns with dashboard's stateless-by-design philosophy (ADR-006) | Restart loses chat history | **Chosen** |
| `SqliteSaver` (file-backed) | Chat history survives restart | Adds a new persistence story + volume mount + eviction; cross-restart chat is marginal value for a localhost diagnostic tool | Deferred — PR 4b can swap if needed |
| Chroma "sessions" collection | Reuses existing vector DB | Abuses a vector store as a KV store | Rejected |

`SessionIndex` (LRU of 200 `thread_id`s) evicts the oldest checkpoint via
`checkpointer.adelete_thread` when the cap is hit. Eviction failures are
logged but swallowed — better to leak a session checkpoint than crash a
request.

### 5. `DASHBOARD_LLM_DRY_RUN=true` — safe-by-default

Cost-safety asymmetry:

- A forgotten env var with default `false` triggers real spend +
  LangSmith trace pollution. Unrecoverable.
- A forgotten env var with default `true` triggers a dry-run banner. The
  operator sees `"DRY_RUN: agent did not contact OpenAI..."` and knows
  the one-line `.env` fix.

The 7d precedent (`DASHBOARD_INGEST_DRY_RUN=false`) is intentionally NOT
mirrored: ingest's purpose IS corpus population, so default-operating
makes sense. Chat's purpose IS paid LLM spend that needs explicit
consent. Different decisions for different defaults.

Implementation uses a custom `_DryRunChatModel` (subclass of
`BaseChatModel`) that inspects input messages:

- If no `ToolMessage` has been seen → return an AIMessage requesting one
  `query_logs` tool call.
- If a `ToolMessage` is present → return the canned final answer.

This exercises the FULL graph topology in tests — analyze → correlate
→ predict → respond — without any network call. CI cannot pay OpenAI even
if a future test mistakenly flips the flag, because `conftest.py`'s
default Settings have dry-run on AND a `fail_if_openai_invoked` fixture
monkeypatches `ChatOpenAI.__init__` to raise.

**2026-06-06 update:** ADR-016 extends this asymmetry to the proactive
scan loop. When `DASHBOARD_LLM_DRY_RUN=true`, the background loop wakes
on schedule, logs `proactive_scan_skipped reason=llm_dry_run`, and skips
graph invocation entirely. Real scans require BOTH `DASHBOARD_LLM_DRY_RUN=false`
AND `DASHBOARD_PROACTIVE_SCAN_ENABLED=true`. Either flag alone is safe.

### 6. Non-streaming response

`POST /api/chat` returns a single JSON `ChatResponse`. The graph runs
`agent.ainvoke(...)`. The frontend shows an animated "Thinking…"
indicator (pure CSS keyframes — no polling) during the 3–10s wait.

`ChatRequest.streaming` is accepted in the schema (forward-compat) but
422'd in the router. PR 4b will replace the rejection with a real SSE
handler without changing the request shape.

Streaming was deferred because:

- ~2× frontend complexity (EventSource, abort-on-unmount, partial-
  citation rendering, mocked-EventSource Vitest tests)
- Audience is an admin operator with LangSmith in another tab
- The contract is strictly additive — adding SSE later doesn't break clients

### 7. Cost-bounding (three caps, all in Settings)

| Setting | Default | Behaviour |
|---|---|---|
| `DASHBOARD_LLM_MAX_TOOL_CALLS_PER_REQUEST` | 4 | Graph short-circuits to `respond` after this many `correlate` passes |
| `DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST` | 8000 | Router counts user message via `tiktoken` (`o200k_base`); over → 413 |
| `DASHBOARD_LLM_MAX_MESSAGES_PER_SESSION` | 40 | (Not yet enforced in 4a; reserved for PR 4b's `SummarizationMiddleware` swap) |

No per-day spend ceiling. LangSmith dashboards + the in-graph caps +
opt-in spend together are sufficient for an admin tool. A real metering
layer is out of scope.

### 8. Credential redaction lives in NEW `dashboard/src/log_dashboard/credentials.py`

Two-layer defence:

1. **Input** — `sanitize_user_input` strips Bearer tokens, `X-API-Key`
   headers, password forms (env / YAML / JSON), JWT-shaped tokens, and
   DSN strings (`scheme://user:pass@host`). Runs in the router AND in
   `ingest_node` (defence in depth — the router log line never sees a
   raw secret, and the graph state is sanitised even if a caller bypasses
   the router).
2. **Output** — `query_logs` runs `sanitize_log_raw` over every cited
   entry's `raw` field BEFORE the `CitedLogEntry` returns from the tool,
   so the LLM never sees a secret-in-log even if a per-app logger
   regression slipped one past the audit baseline. The same sanitiser
   also flows over the final `AIMessage.content` and over
   `Citation.raw` in the response.

`credentials.py` is **new code only**. The Agitator's existing
`agitator/runs.py::_sanitize_error` is left untouched. Reasons:

- `feedback_behavior_preserving_refactor_gate` — touching Agitator's
  code from a feature PR would change its behaviour (DSN redaction would
  start firing on its `last_error` field)
- `feedback_remediation_pr_granularity` — dedupe is a separate concern,
  queued as a small follow-up chore PR after Phase 7 closes
- ~10 lines of duplicated JWT/needle constants is an acceptable
  transient cost; the duplication is small, well-confined, and tested
  independently in both modules

### 9. No proactive-loop stub

The `.claude/rules/dashboard.md` "proactive loop" is a real future
requirement (PR 4c). PR 4a does NOT ship a `noop_scan` stub:

- ~5 lines of dead code with no behaviour
- The actual complexity of PR 4c is the SCAN LOGIC (what counts as an
  anomaly, scan cadence, alert surface) — not the scheduler glue
- `/ultrareview` would correctly flag a dead-code stub as YAGNI

PR 4c will add the scheduler + flag + scan body together.

## Consequences

- The chat agent works against the corpus 7d populates, against the live
  status the 7b machinery surfaces, with full credential safety baked in.
- Cost is bounded by three deterministic caps + a safe-by-default dry-run.
- The LangSmith trace name + metadata (`session_id`, `jwt_sub`) make
  agent runs filterable in the LangSmith UI.
- PR 4b can build Error Detail on top of the same agent graph by reusing
  `build_agent_graph` with a different initial state. The contract is
  stable.
- PR 4c can drop in a scan body and reuse the same tool surface
  (`query_logs` + `get_app_status`) and the same chat-model factory.
- Agitator's `_sanitize_error` is untouched; the planned dedupe is
  tracked as a follow-up chore PR.

## Amendment 2026-06-08 — Phase 8 supersedes the cost-asymmetry rationale (ADR-017)

Phase 8 ([ADR-017](ADR-017-local-ai-via-ollama.md)) replaces OpenAI with locally-run
models via Ollama. External inference cost goes to zero. This rescinds the
load-bearing justification for §5's `DASHBOARD_LLM_DRY_RUN=true` runtime default.

**Changes:**

- **Runtime default flips: `DASHBOARD_LLM_DRY_RUN=false`.** No surprise spend possible
  (no external API to charge). Operators get real Ollama responses by default
- **Test-harness default stays `true`** via a new autouse fixture in
  `dashboard/tests/conftest.py`. Tests don't pay for real LLM inference time
  (local Ollama calls take seconds; tests should take milliseconds)
- **`_DryRunChatModel` is preserved** — same `BaseChatModel` interface; the swap from
  `ChatOpenAI` to `ChatOllama` is transparent to the dry-run model
- **`fail_if_openai_invoked` is renamed `fail_if_real_llm_invoked`** and monkeypatches
  `ChatOllama.__init__` instead of `ChatOpenAI.__init__`. Defence-in-depth preserved
- **Decisions §1, §2, §3, §4, §6, §7, §8 are UNCHANGED.** Only §5's cost-asymmetry
  rationale evolves. The 5-node topology, manual tool dispatch, session memory,
  cost caps (as values), credential redaction, and the non-streaming/SSE-streaming
  contract all remain in force

See ADR-017 for the full Phase 8 design.

## Amendment 2026-06-07 — credential-detection dedup landed

The follow-up chore PR referenced in §8 and the Consequences section
shipped on 2026-06-07. A new `dashboard/src/log_dashboard/credential_patterns.py`
module owns the shared shape detection — the JWT-shape regex and the
sensitive-keyword vocabulary (`authorization` / `bearer` / `x-api-key` /
`password`). Both `credentials.py` and `agitator/runs.py::_sanitize_error`
import from it.

Each consumer keeps its policy: `credentials.py` continues surgical
substitution with `[REDACTED]`; `_sanitize_error` continues
drop-whole-message with its sentinel strings. The DSN regex stays local
to `credentials.py` (drop-policy doesn't need it). Behavior-preserving
per `feedback_behavior_preserving_refactor_gate` — existing 36 tests
across `test_credentials.py`, `test_agitator_sanitize.py`, and
`test_agent_credential_redaction.py` pass unchanged; a new
`test_credential_patterns.py` adds 17 tests for the shared primitives.
