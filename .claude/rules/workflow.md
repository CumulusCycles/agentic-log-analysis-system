# Project Rules — Git & Workflow

> **Canonical reference:** `docs/development-workflow.md` — extended documentation,
> workflow diagrams, troubleshooting, and best practices. This file is the compact
> runtime reference for Claude Code; the docs file governs when they conflict.

## Branching
- Never commit directly to `main`
- Always create a feature branch before starting work
- Branch naming: `feature/<short-description>` or `fix/<short-description>`
- Scope by app where relevant: `feature/fnol-routes`, `fix/customer-portal-auth`

## Commit Conventions
- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`
- Scope by app: `feat(fnol):`, `fix(customer-portal):`, `chore(docker):`
- Keep commits atomic — one logical change per commit

## Pull Requests
- All changes via PR — even solo work
- PR title follows same convention as commit messages
- Include a brief description of what changed and why

## Pre-Ship Checklist — Before Every /ship

1. **`CLAUDE.md` is current** — reflects any new decisions or conventions
2. **`PLAN.md` is current** — mark completed `✅`, in-progress `🔄`, add new tasks
3. **Relevant `.claude/rules/*.md` files are current**
4. **`README.md` phase table is accurate**
5. **`docs/` is current** — architecture, tech stack, decisions
6. **File names comply** — `docs/tech/file-naming-convention.md` and `.claude/rules/file-naming.md`

**Why this matters:** Once a PR is merged and the branch is deleted, undocumented decisions are lost.

---

## Build Checkpoints (target state per phase, commit after each)
1. **Phase 1** — Repo skeleton complete (all config, docs, `.claude/`, `.env.example`)
2. **Phase 2** — Root `docker-compose.yml` with all 8 containers, volumes, healthchecks
3. **Phase 3** — Shared Data API running and healthy
4. **Phase 4** — FNOL running and logging to volume
5. **Phase 5** — Customer Portal running and logging
6. **Phase 6** — Agent Portal running and logging; all containers + DBs stable together
7. **Phase 7a** — Dashboard scaffold + standalone JWT auth (FastAPI + React + container)
8. **Phase 7b** — Dashboard log ingestion (4 log volumes → `/api/logs` + `/api/status`)
9. **Phase 7c** — Dashboard UI (Overview + Log Explorer screens)
10. **Phase 7d** — Dashboard Chroma + embeddings pipeline
11. **Phase 7e** — Dashboard LangGraph agent + AI Chat + Error Detail (the LLM work)

## Claude Code Hooks
- `.claude/hooks/pre_bash_guard.sh` — blocks dangerous commands
- `.claude/hooks/post_format.sh` — auto-formats Python, JS/TS, JSON after file save
- `.claude/hooks/post_compose_validate.sh` — validates docker-compose.yml after edits
