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
- `.claude/hooks/ship_audit.sh` — invoked as `/ship` Step 1; fails closed if any tool prescribed by `/ship` or `/lint` is not bound in CI (Node `format:check`, Python `ruff`+`black`, Java `maven-checkstyle-plugin` phase binding, per-app `ci-*.yml` enforcement). No `--skip` flag by design. Why: PRs #29 and #30 both surfaced dormant gates — tools in process docs that CI never ran.

---

## Agentreviewer (`/ultrareview`)

**What:** Claude Code's built-in multi-agent cloud review. Several Claude
agents inspect the PR in parallel from different angles (design,
correctness, security, cross-file consistency, test coverage). Referred to
as **agentreviewer** in this project.

**Trigger:** the operator types `/ultrareview <PR#>` (or bare
`/ultrareview` for the local branch). **Claude cannot launch it** —
billed cloud review, user-triggered only.

**Use it on:**
- PR 2 — chaos middleware (first real exercise on this codebase)
- PR 3 — Agitator (bundled-in-dashboard architecture call)
- PR 4 — Phase 7e LangGraph (non-negotiable; the LLM slice)
- Any future cross-cutting middleware, LangGraph, or Phase 7e+ work

**Skip on:** single-file doc edits, lockfile bumps, ADR-only PRs.

**Model preference:** Opus 4.7 across all reviewer agents (deep design,
security, test-coverage gap analysis). Sonnet 4.6 acceptable for
breadth-only roles if the tool exposes per-agent selection. Never Haiku
for high-stakes PRs.

**Pre-flight (run once before the first invocation on this codebase):**

```bash
# 1. .env is gitignored and untracked
git check-ignore .env && [ -z "$(git ls-files .env)" ] && echo OK-env-untracked

# 2. .env.example has only placeholder values — no real secrets
grep -vE '^#|^$|=changeme$|=example$|=your-.*-here$|=placeholder' .env.example

# 3. No real secrets accidentally committed in source
grep -rE 'sk-[A-Za-z0-9]{20,}|xoxb-|ghp_|AKIA[0-9A-Z]{16}' \
  --include='*.py' --include='*.ts' --include='*.tsx' \
  --include='*.java' --include='*.json' --include='*.yml' \
  apps/ dashboard/ docs/ .github/ .claude/ || echo OK-no-hardcoded-secrets
```

All three must pass before the first agentreviewer run. Re-run only if
`.env.example` or secret-handling code changes materially.

**Finding-triage workflow:**
1. Operator runs `/ship` — audit, doc check, reviews, lint, build, tests, PR opens, CI goes green
2. Operator runs `/ultrareview <PR#>`
3. Operator surfaces findings to Claude (paste, or `gh pr view <PR#> --comments`)
4. Claude triages each finding: fix in code, push fix commit, or push back with rationale
5. Re-run agentreviewer if findings were structural

Full long-form policy + workflows: `docs/development-workflow.md`.
