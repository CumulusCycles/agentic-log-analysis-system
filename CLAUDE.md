# Agentic Log Analysis System — Project Guidance for Claude Code

This file provides project-specific guidance for Claude Code.
Global behavior is defined in the global `CLAUDE.md`.

For a complete inventory of all Claude Code resources in this project (agents, commands,
hooks, skills, rules) and when they are invoked, see `CLAUDE_RESOURCES.md`.

The complete build task list is in `PLAN.md` — update it before every `/ship`.

---

## Security

- **NEVER READ FROM OR WRITE TO `.env` FILES** — Only read/write `.env.example` templates
- Never commit `.env` files — use `.env.example` only
- API keys live in `.env` — never reference them directly in code
- **NEVER LOG CREDENTIALS** — passwords, JWT secrets, API keys, bearer tokens, DB connection strings, LLM keys, admin creds, or ANY `.env` value must never appear in any log line, error message, exception trace, or response body. See `.claude/rules/logging.md` §Non-Negotiable Rules and the `feedback_never_log_credentials` memory for the full decision tree. Audit baseline: every app's logger calls verified clean as of 2026-06-04.
- Security-header middleware (`helmet` / Spring Security defaults / FastAPI middleware) intentionally skipped per ADR-010 — local-only deployment. Backfill required before any non-localhost exposure.
- **`ENABLE_CHAOS` is a dev-only switch.** When `true`, the chaos middleware on SDA/FNOL/CP/AP honors `X-Chaos: slow:<ms>` and `X-Chaos: error:<status>` directives to simulate failures. Default `false`; ADR-013 documents the design + stack positions. Never default this to `true` in any deployment. Per ADR-001, the local-only threat model bounds the surface; this is a deliberate dev-time tool.

---

## Project Rules

Detailed rules are in `.claude/rules/`:

| File | Coverage |
| --- | --- |
| `.claude/rules/project.md` | Repo structure, architecture overview, container topology, volumes |
| `.claude/rules/workflow.md` | Git branching, commit conventions, PRs, pre-ship checklist |
| `.claude/rules/apps.md` | Per-app stack conventions (Shared Data API, FNOL, Customer Portal, Agent Portal, Agentic Log Analysis Dashboard) |
| `.claude/rules/logging.md` | Logging strategy, formats per stack, volume paths |
| `.claude/rules/dashboard.md` | Agentic Log Analysis Dashboard app conventions |
| `.claude/rules/infrastructure.md` | Docker Compose, container config, ARM64, M1 notes |
| `.claude/rules/file-naming.md` | File and path naming — mandatory for all new files and renames |

**File names:** Follow `docs/tech/file-naming-convention.md` (enforced via `.claude/rules/file-naming.md`).

---

## Quick Reference

- **Model:** `settings.json` sets `claude-sonnet-4-6`; `settings.local.json` may override locally (e.g., `opus`) — local override is gitignored and not team policy
- **Package manager:** Always `pnpm` for Node/JS — never `npm` or `yarn`
- **Python:** Always `uv` — never `pip` directly
- **Branching:** Never commit directly to `main` — always feature branch + PR
- **Docs:** Read `docs/` before building anything
- **One app at a time:** Fully scaffold and verify one app before moving to the next
- **ARM64:** All Docker images must be ARM64-compatible (M1 Max host)
- **No cloud deployment for the apps:** Local Docker Compose only — no AWS, CDK, no remote app hosting
- **CI:** GitHub Actions runs lint + unit tests + build on every PR via a single consolidated `.github/workflows/ci.yml` — `dorny/paths-filter@v3` `changes` job + 5 conditional per-app jobs (`shared-data-api`, `fnol`, `customer-portal`, `agent-portal`, `dashboard`). See ADR-012 (supersedes ADR-009). E2E stays local via `/ship`.
- **GitHub operations:** Always use `gh` CLI

---

## Commands

- `/self-review` — query MCP docs → review written code against best practices → fix issues
- `/security-review` — scan for secrets, injection, auth gaps, exposed internals → fix issues
- `/ship` — Step 1 audit (`.claude/hooks/ship_audit.sh`) → pre-ship doc check → self-review → security-review → lint → build → test → commit → push → open PR
- `/done` — post-merge cleanup: checkout main, pull, delete local + remote branch
- `/test` — run tests for the current app or all apps
- `/lint` — run linting and formatting checks
- `/build` — run production build and report errors
- `/logs` — tail live container logs
- **agentreviewer** — multi-agent cloud review for high-stakes PRs (PR 2 chaos, PR 3 Agitator, PR 4 Phase 7e). Invoked via the Claude Code built-in `/ultrareview <PR#>`; **user-triggered only — Claude cannot launch it.** Model preference: Opus 4.7. Full policy + pre-flight + workflow: `.claude/rules/workflow.md` and `docs/development-workflow.md`.

---

## Agents

See `.claude/agents/` for full details.
- **git-agent** — all git and GitHub operations via `git` and `gh` CLI
- **docker-agent** — Docker Compose, containers, volumes
- **python-agent** — Python app development for Shared Data API and FNOL (always uses `uv`)

---

## MCP Servers

See `.mcp.json` for configuration.
- **context7** — up-to-date library docs for all apps (including dashboard frontend)
- **playwright** — browser automation and UI testing
- **docs-langchain** — LangChain, LangGraph, and LangSmith docs (dashboard backend only)

**MCP usage rule:**
- Dashboard backend (LangGraph agent, Chroma, ingestion pipeline) → use **docs-langchain**
- All other apps + dashboard frontend → use **context7**

**ALWAYS query the appropriate MCP server before writing code for any library, framework, or SDK.** Never rely on training data alone — live docs are the source of truth for API signatures, patterns, and best practices.
