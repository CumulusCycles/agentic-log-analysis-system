# Architecture

System-level architecture documents — how the containers fit together (8 in Phase 7; 9 long-running + 1 init in Phase 8 / [ADR-017](../decisions/ADR-017-local-ai-via-ollama.md)), where data flows, and which services depend on which.

Decisions that shaped this architecture live in [`../decisions/`](../decisions/). Operator-facing runbooks live in [`../operations/`](../operations/).

## Files

| File | Covers |
|---|---|
| [`system-overview.md`](system-overview.md) | Quick-reference data — port table, healthcheck commands, startup dependency order. Cross-links to the diagrammatic docs below |
| [`system-integration.md`](system-integration.md) | Wide-view integration narrative across all components — data layer, two-system auth, per-app request flows, background simulator, log volumes, X-Source propagation, ingest pipeline, dashboard data paths, LangGraph agent topology, Agitator scenarios, chaos cascade. 14 Mermaid diagrams |
| [`log-flow.md`](log-flow.md) | Deep-slice walkthrough of one log line — Browser → FNOL → SDA → structlog → `fnol-logs` volume → dashboard read-only mount → watchdog → parser → ingest gate → Chroma — with the human path (`/api/logs`, unfiltered) branching off at the volume |

## Visual diagrams

Polished HTML diagrams now live in [`/site/`](../../site/) — open locally in a browser, or serve via GitHub Pages.

| File | Covers |
|---|---|
| [`site/index.html`](../../site/index.html) | Landing page — entry point with cross-links to all three diagrams and the markdown source |
| [`site/system-overview.html`](../../site/system-overview.html) | Visual rendering of the quick-reference data in `system-overview.md` — port grid, healthcheck probe list, startup dependency DAG. Same dark-themed HTML/CSS sibling style |
| [`site/log-flow.html`](../../site/log-flow.html) | Visual rendering of the log-flow walkthrough — dark-themed HTML/CSS, sibling style to `docker-architecture.html`. Open locally in a browser — not GitHub-rendered |
| [`site/docker-architecture.html`](../../site/docker-architecture.html) | Visual rendering of the Docker infrastructure — host / Docker Desktop / `insurance-net` boundaries, 9 long-running containers in two tiers (apps + DB/AI), 8 persistent volumes, local Ollama AI container (Phase 8 / ADR-017; replaces the prior OpenAI external API box), data/log/auth/startup flow boxes. Self-contained HTML/CSS — open locally |
