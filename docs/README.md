# Documentation Index

Read these docs before building. They define the decisions, architecture, and conventions
that all implementation must follow.

---

## Start Here

| File | What it covers |
|---|---|
| [`project-brief.md`](project-brief.md) | Narrative overview — what this system is, why it exists, and what the primary deliverable is |
| [`development-workflow.md`](development-workflow.md) | Hooks, slash commands, review flow, and phase checkpoints |

---

## Subdirectories

Each subdirectory has its own README with a per-file index and any local conventions.

| Directory | What's in it |
|---|---|
| [`architecture/`](architecture/) | System architecture — container topology, log-flow diagram, port reference, startup dependencies |
| [`decisions/`](decisions/) | Architecture Decision Records (ADRs 001–017) + supersession + amendment conventions |
| [`operations/`](operations/) | Operator-facing runbooks for the running stack (Agitator, chaos, embedding wall-time, Proactive Scan) |
| [`tech/`](tech/) | Long-form tech reference — stack, logging strategy, log-event catalog, data model, file-naming convention |
