# Claude Code Resources — Complete Inventory

This file lists every Claude Code resource in this project, what it does, and when it is invoked.

---

## Commands (`/` prefix)

| Command | File | When to Use |
|---|---|---|
| `/self-review` | `.claude/commands/self-review.md` | After writing code, before running tests — query MCP docs, review diff, fix issues |
| `/ship` | `.claude/commands/ship.md` | Ready to commit and open a PR — runs pre-ship doc check → self-review → security-review → lint → build → **every app's test suite (backend + frontend unit + Playwright E2E)** → commit → push → PR |
| `/done` | `.claude/commands/done.md` | After a PR is merged — checkout main, pull, delete local + remote branch |
| `/test` | `.claude/commands/test.md` | Run tests for the current app, a single named app, or `/test all` for every app's suite (mirrors `/ship`'s gate) |
| `/lint` | `.claude/commands/lint.md` | Run linting and formatting checks for the current app |
| `/build` | `.claude/commands/build.md` | Run a production build and report errors |
| `/logs` | `.claude/commands/logs.md` | Tail live Docker container logs |
| `/security-review` | `.claude/commands/security-review.md` | Before shipping — scan for secrets, injection, auth gaps, exposed internals |

---

## Agents (`.claude/agents/`)

| Agent | File | When to Use |
|---|---|---|
| `git-agent` | `.claude/agents/git-agent.md` | All git and GitHub operations — commits, branches, PRs, cleanup |
| `docker-agent` | `.claude/agents/docker-agent.md` | Docker Compose, container debugging, volume inspection, ARM64 checks |
| `python-agent` | `.claude/agents/python-agent.md` | Shared Data API and FNOL Python development (always uses `uv`) |

---

## Skills (auto-triggered)

| Skill | File | Trigger |
|---|---|---|
| `docker-validate` | `.claude/skills/docker-validate/SKILL.md` | After editing docker-compose.yml or changing base images |
| `log-analysis` | `.claude/skills/log-analysis/SKILL.md` | When asked to read, debug, or inspect Docker volume log output |

---

## Hooks (automatic)

| Hook | File | Trigger |
|---|---|---|
| `pre_bash_guard` | `.claude/hooks/pre_bash_guard.sh` | Before every Bash command — blocks `docker compose down -v`, dangerous `rm`, `.env` reads and writes |
| `post_format` | `.claude/hooks/post_format.sh` | After every file write/edit — auto-formats Python (black), JS/TS/JSON (prettier) |
| `post_compose_validate` | `.claude/hooks/post_compose_validate.sh` | After editing docker-compose.yml — validates syntax and ARM64 platform flags |

---

## Rules (always loaded)

| File | Coverage |
|---|---|
| `.claude/rules/project.md` | Repo structure, architecture overview, container topology, volumes |
| `.claude/rules/workflow.md` | Git branching, commit conventions, PRs, pre-ship checklist |
| `.claude/rules/apps.md` | Per-app stack conventions, routes, DB tables, seed data |
| `.claude/rules/logging.md` | Logging strategy, per-stack formats, volume mount paths |
| `.claude/rules/dashboard.md` | Agentic Log Analysis Dashboard: LangGraph agent, Chroma, UI screens, MCP server usage |
| `.claude/rules/infrastructure.md` | Docker Compose, ARM64 images, port assignments, persistent volumes |
| `.claude/rules/file-naming.md` | Mandatory file naming — see `docs/tech/file-naming-convention.md` |

---

## MCP Servers (`.mcp.json`)

| Server | When to Use |
|---|---|
| `context7` | Writing code for any app or the dashboard frontend — fetch current library/framework docs |
| `docs-langchain` | Writing dashboard backend code — LangChain, LangGraph, LangSmith, Chroma docs |
| `playwright` | Browser automation and UI testing |
