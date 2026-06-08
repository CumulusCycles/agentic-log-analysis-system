# Architecture

System-level architecture documents — how the eight containers fit together, where data flows, and which services depend on which.

Decisions that shaped this architecture live in [`../decisions/`](../decisions/). Operator-facing runbooks live in [`../operations/`](../operations/).

## Files

| File | Covers |
|---|---|
| [`system-overview.md`](system-overview.md) | Quick-reference data — port table, healthcheck commands, startup dependency order. Cross-links to the diagrammatic docs below |
| [`system-integration.md`](system-integration.md) | Wide-view integration narrative across all components — data layer, two-system auth, per-app request flows, background simulator, log volumes, X-Source propagation, ingest pipeline, dashboard data paths, LangGraph agent topology, Agitator scenarios, chaos cascade. 14 Mermaid diagrams |
| [`log-flow.md`](log-flow.md) | Deep-slice walkthrough of one log line — Browser → FNOL → SDA → structlog → `fnol-logs` volume → dashboard read-only mount → watchdog → parser → ingest gate → Chroma — with the human path (`/api/logs`, unfiltered) branching off at the volume |
| [`log-flow.html`](log-flow.html) | Visual rendering of the log-flow walkthrough — dark-themed HTML/CSS, sibling style to `docker-architecture.html`. Open locally in a browser — not GitHub-rendered |
| [`docker-architecture.html`](docker-architecture.html) | Visual rendering of the Docker infrastructure — host / Docker Desktop / `insurance-net` boundaries, 8 containers in two tiers (apps + DB/vector), 7 persistent volumes, OpenAI external API, data/log/auth/startup flow boxes. Self-contained HTML/CSS — open locally |
