# ADR-017 — Local AI via Ollama replaces OpenAI for embeddings and LLM (Phase 8)

**Status**: Accepted
**Date**: 2026-06-08
**Supersedes**: none
**Amends**: ADR-015 §5 (cost-asymmetry rationale), ADR-016 (cost matrix → fires/skips matrix)
**Related**: ADR-001 (local-only), ADR-006 (standalone dashboard auth), ADR-013 (chaos
middleware — ERROR-tier signal), ADR-014 (Agitator), ADR-015 (LangGraph agent),
ADR-016 (proactive scan)

## Context

Phase 7 closed 2026-06-06 with the dashboard's primary deliverable intact — an agentic
log-analysis system backed by `gpt-4o` + `text-embedding-3-small`. v1.0.0 shipped
2026-06-08 and the repo went public the same day.

Two structural limitations follow from the OpenAI dependency:

1. **Cost-driven WARN+ERROR-only ingest gate.** `DASHBOARD_INGEST_LEVELS=WARN,ERROR`
   exists because every embedding costs ~$0.00002 (`text-embedding-3-small` list price).
   The agent's retrieval surface (Chroma) ends up at ~6% of total log volume — only
   errors. The LangGraph agent can answer "what's broken?" but is structurally blind
   to "what does normal look like?" Baseline awareness is impossible because the
   baseline (INFO entries) is never in the corpus.

2. **Public-repo demo is canned by default.** ADR-015 §5 documents the `DRY_RUN=true`
   safe-by-default rationale — a forgotten env var must never trigger surprise spend.
   The cost is real: anyone cloning the public repo without an OpenAI key sees canned
   responses in the AI Chat surface until they wire up paid inference.

The project brief promises "**proactively predict problems before they escalate**" —
which structurally requires seeing baseline INFO, not just errors. The cost barrier
prevents that.

Phase 8 replaces OpenAI with locally-run models via Ollama in a Docker container.
Inference becomes free. The level gate goes away. Chroma admits all levels. The agent
gains the baseline awareness the project's purpose requires.

## Decisions

### 1. Ollama is the local-inference runtime

`ollama` ships as a 9th container in `docker-compose.yml`, sized for M1 Max Metal
acceleration (Apple's unified memory model means GPU + CPU share the same RAM pool;
no separate VRAM constraint).

Alternatives considered:

| Runtime | Decision | Why |
|---|---|---|
| **Ollama** | ✅ Chosen | Mature OpenAI-compatible API; first-class LangChain integration (`langchain-ollama`); Docker image with Metal support; model management built in (`ollama pull`); persistent model storage via standard volume |
| `llama.cpp` directly | Rejected | More work to wrap with a stable HTTP API; manual model management; would reimplement what Ollama provides |
| `mlx-lm` (Apple-native) | Rejected | Mac-only; would lock the project to Apple Silicon; Ollama already uses Metal under the hood |
| Replace with another paid API (Anthropic, Groq, etc.) | Rejected | Solves cost but not the public-repo demo problem; still requires an API key in `.env` |

### 2. Model picks: `nomic-embed-text` (embeddings) + `llama3.1:8b` (LLM)

| Role | Model | Dimensions / Size | Rationale |
|---|---|---|---|
| Embeddings | `nomic-embed-text` | 768-dim · ~300MB · 8192-token context | Comparable quality to `text-embedding-3-small` for structured technical text; ~50ms per embedding on M1 Max — faster than OpenAI API round-trip latency |
| LLM | `llama3.1:8b` (Q4 quantized) | ~4.5GB RAM · 8B params | Pattern-matching workload (latency clusters, rate anomalies, baseline comparison) fits comfortably within 8B model capabilities. ~15 tok/sec inference on M1 Max via Metal |

**Upgrade path documented but not adopted:** If the agent's reasoning quality is
insufficient in practice, swap to `qwen2.5:14b` (~9GB, ~8 tok/sec, better reasoning).
The swap is a `.env` change + `ollama pull` — no Chroma re-embed because the
embedding model is independent of the LLM model.

**Alternative embedding model considered:** `mxbai-embed-large` (1024-dim, ~600MB,
slightly better retrieval quality). Defer until retrieval quality complaints surface;
`nomic-embed-text` is the smaller / faster / sufficient default.

### 3. Chroma migration: wipe + re-embed (Option A)

`text-embedding-3-small` produces 1536-dim vectors; `nomic-embed-text` produces
768-dim. These dimensions are **incompatible** in the same Chroma collection.

Options considered:

| Option | Decision | Why |
|---|---|---|
| **A. Wipe `chroma-data` volume + re-embed from log volumes** | ✅ Chosen | Clean slate. Log volumes are the durable record; Chroma is a derived index. Operator-driven step in dashboard-guide.md. Idempotent. Free (local embeddings). Takes ~minutes on M1 Max |
| B. New collection name (`log_entries_v2`) | Rejected | Leaves orphan old collection in the volume forever. No upside |
| C. Auto-detect-and-wipe on startup | Rejected | Hidden destructive behaviour. Operator should know when Chroma is rebuilt |

The Phase 8 implementation PR (PR 8b) documents the wipe as a runbook step:

```bash
docker compose down
docker volume rm agentic-log-analysis-system_chroma-data
docker compose up -d --build
```

### 4. Ingest level gate removal — admit all levels

`DASHBOARD_INGEST_LEVELS` default changes from `WARN,ERROR` (Phase 7) to
`DEBUG,INFO,WARN,ERROR` (Phase 8). This is the **load-bearing reason for Phase 8** —
it's what gives the agent baseline awareness.

**The other two ingest gates stay:**

- **Source gate** (`DASHBOARD_INGEST_SOURCES=prod,synthetic,unknown` — unchanged)
  exists for **signal quality**, not cost. Playwright `test` traffic and
  parser-derived `health` healthcheck pings are noise regardless of inference cost
- **Content-hash dedup** (`{app}:sha1(raw)[:16]}` IDs) exists for **performance**,
  not cost. Avoiding re-embedding identical lines on restart is correct whether the
  embedding model is paid or free

This decision is **not just a model swap** — it's a substantive policy change. The
agent's diagnostic ceiling rises from "what errors are happening?" to "what's
abnormal compared to recent normal behavior?" via RAG: when the agent's `query_logs`
tool fetches "FNOL submit response times," it now returns INFO entries with actual
`duration_ms` values to compute a baseline from. The model itself stays frozen — what
expands is the retrieval surface.

### 5. Resource budget — Docker Desktop 32GB allocation

Phase 7 baseline: ~2.5GB Docker RAM across 8 containers. Phase 8 adds:

| Container / model | Approximate RAM |
|---|---|
| Ollama base process | ~200MB |
| `nomic-embed-text` (loaded) | ~300MB |
| `llama3.1:8b` Q4 (loaded) | ~4.5GB |
| **Phase 8 total** | **~7.5GB** |

Docker Desktop allocation: bump from 20GB to **32GB** in
Settings → Resources. 32GB leaves ~24GB headroom for macOS, browsers, IDEs, etc.
on a 64GB M1 Max.

### 6. Ollama port is internal-only

`ollama` does **not** publish port 11434 to the host. The container is reachable
only from `insurance-net` (the dashboard's bridge network). This matches the Chroma
posture — both AI-infrastructure services stay internal.

Alternatives considered:

| Approach | Decision | Why |
|---|---|---|
| Internal-only (no host port) | ✅ Chosen | Smaller public-repo attack surface; matches Chroma; aligns with ADR-001 local-only threat model. The dashboard's `/api/chat` is the operator's entry point for Ollama interaction; direct `curl` to Ollama is not a documented operator workflow |
| Host-exposed `11434:11434` | Rejected | "Useful for direct curl testing" is a dev-time convenience, not a runtime requirement. Adds a host port that's visible in `lsof`/`netstat` output for no production purpose |

If an operator wants direct Ollama access for ad-hoc testing, they can exec into the
container: `docker compose exec ollama ollama run llama3.1:8b`.

### 7. Tokenizer cap uses a character-count heuristic

`DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST=8000` is a **safety bound, not a billing
meter**. It exists to reject pathologically large user inputs at the router boundary
(returns 413). Precision doesn't matter; safety does.

Phase 7 implementation: `tiktoken.encoding_for_model("gpt-4o")` with fallback to
`o200k_base` encoding. Phase 8 replaces this with `len(text) // 4` — a
character-count heuristic that approximates tokens at ~4 chars per token (close
enough for English text under any modern tokenizer).

| Option | Decision | Why |
|---|---|---|
| `len(text) // 4` heuristic | ✅ Chosen | Zero deps; provider-agnostic; precision is unnecessary for a safety bound |
| `tiktoken.get_encoding("cl100k_base")` (older OpenAI) | Rejected | Wrong tokenizer for Llama; produces wrong count; misleading |
| Hugging Face `tokenizers` with llama tokenizer | Rejected | New dependency + tokenizer config + version drift surface area, all for marginal precision on a cap that doesn't need it |
| Word-count split | Rejected | Less accurate than char-count for token estimation; same dep cost |

`tiktoken` drops from `dashboard/pyproject.toml`. The cap value (8000) stays.

### 8. Chat-time system prompt injection for baseline-direction

Exploration during Phase 8 planning surfaced that `routers/chat.py` has **no system
prompt** today — the user query is the sole `HumanMessage`. With the corpus expansion
in Decision 4, the agent has the data to do baseline analysis but no direction to
USE it.

PR 8b adds a `SystemMessage` to the `analyze` node of the LangGraph agent, injected
once per chat session (when `state.messages` contains exactly one `HumanMessage` —
the first call). Content directs the agent to:

- Query `query_logs` for INFO entries showing recent normal behavior when relevant
- Compare WARN/ERROR observations against the baseline frequency / patterns / rates
- Cite specific log entries (existing behavior, reinforced)

The SystemMessage is **not** injected on subsequent passes through `analyze` (the
post-tool-call returns) — the message budget calculation depends on the message list
size; double-counting would skew the cap.

The `PROACTIVE_SCAN_PROMPT` (in `agent/proactive_prompt.py`) is revised in PR 8b to
incorporate the same baseline-direction framing.

## Consequences

- **The agent gains baseline awareness.** Diagnostic ceiling rises from "what's
  broken?" to "what's abnormal compared to normal?" — the project brief's
  "proactively predict problems before they escalate" becomes structurally possible
- **No `OPENAI_API_KEY` required.** Removed from `.env.example`. Public-repo demo
  works out-of-the-box once the first-boot model pull completes
- **AI Chat latency increases.** ~1–3s (OpenAI) → ~5–30s (local llama3.1:8b on M1 Max).
  SSE streaming from PR #38 masks this somewhat; UI shows the response as it generates
- **Docker Desktop allocation must be 32GB.** Operator-side prerequisite. Documented
  in `README.md` + `docs/operations/dashboard-guide.md`
- **First-boot model pull is ~5–15 minutes.** Runs once on first
  `docker compose up -d --build`, pulls both models to the `ollama-data` volume.
  Subsequent boots use cached weights
- **Chroma must be wiped during PR 8b deployment.** One-time operator action.
  Documented in dashboard-guide.md
- **`DASHBOARD_LLM_DRY_RUN` runtime default flips from `true` to `false`.** No cost
  asymmetry to gate. Mechanism kept as test-harness convenience (tests use
  autouse fixture to set `true`)
- **Embed-summary table loses USD columns.** Phase 7 printed `batch_cost_usd` +
  `session_cost_usd`. Phase 8 replaces with `batch_wall_ms` + `session_wall_ms` —
  same observability shape, different units
- **`is_openai_api_error` becomes `is_llm_api_error`** in `agent/responses.py`,
  catching broader exception classes (httpx HTTP errors, connection errors,
  timeouts) rather than `openai.APIError` specifically
- **LangSmith continues to work unchanged.** Provider-agnostic; traces both
  `ChatOpenAI` and `ChatOllama` calls via the same callback machinery
- **Supporting apps (SDA, FNOL, CP, AP) are completely untouched.** Phase 8 is
  dashboard-side only; verified zero OpenAI references in `apps/**` during planning
- **The frontend is completely untouched.** Same API contracts; same UI components;
  same Vitest + Playwright tests (minor matcher updates for 503 messaging)
- **ADR-015 §5 amended.** The cost-asymmetry rationale was the load-bearing
  justification for `DRY_RUN=true` default. Amendment block points to this ADR and
  notes the runtime-default flip
- **ADR-016 amended.** The cost matrix (line 35) becomes a "fires/skips" matrix —
  the loop still skips when `DRY_RUN=true`, but for noise-control reasons (the dry-run
  model returns the same canned response every time), not cost reasons

## What this ADR does NOT change

- **LangGraph 5-node StateGraph topology** (ADR-015 §1) — unchanged
- **Manual tool dispatch** (ADR-015 §3) — unchanged
- **`InMemorySaver` session memory + `SessionIndex` LRU eviction** (ADR-015 §4) —
  unchanged
- **Cost caps** (ADR-015 §7) — values unchanged (`MAX_TOOL_CALLS_PER_REQUEST=4`,
  `MAX_INPUT_TOKENS_PER_REQUEST=8000`, `MAX_MESSAGES_PER_SESSION=40`). Rationale
  shifts from "cost bounding" to "performance / UX bounding"
- **Credential redaction at input + output boundaries** (ADR-015 §8) — unchanged
- **Tool surface** (`query_logs` + `get_app_status`) — unchanged
- **Chroma collection name + metadata schema** — unchanged (only vectors change)
- **Proactive scan opt-in chain** (ADR-016 §3) — both flags still required for real
  scans; mechanism preserved
- **Severity-from-citations rule** (ADR-016 §7) — unchanged
- **Source gate + content-hash dedup** (ingest pipeline) — unchanged
- **Supporting apps** (SDA, FNOL, CP, AP) — unchanged
- **All API routes and contracts** — unchanged
- **Auth, X-Source propagation, chaos middleware, Agitator** — all unchanged

## PR sequence

Phase 8 ships in two PRs:

- **PR 8a** — Documentation + ADRs only. This file + amendment blocks on ADR-015
  + ADR-016 + the ~17 other doc updates. No code change. No runtime behavior change
- **PR 8b** — Implementation. Compose file, `.env.example`, `pyproject.toml` deps,
  the code call-sites, the test rework, the prompt revisions, the Chroma migration
  runbook step, live-stack validation

Per `feedback_split_pr_for_big_pivots` — docs-first split for big architectural
pivots.

## References

- ADR-015 — Phase 7e LangGraph agent (Decision §5 amended by this ADR)
- ADR-016 — Proactive background scan (cost-matrix amended by this ADR)
- ADR-001 — Local Docker only (this ADR doubles down on the local-only ethos)
- `feedback_split_pr_for_big_pivots` — informs the 2-PR split
- `feedback_never_log_credentials` — credential-redaction posture preserved
- `feedback_ship_skip_e2e_still_needs_smoke` — PR 8b needs live-stack validation
- `project_phase_8_local_ai_plan` (memory) — parked planning notes
