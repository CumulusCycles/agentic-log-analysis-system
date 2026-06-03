# Development Workflow — Agentic Code Review & Automation

This document describes the **planned** development workflow for this project: local
Claude Code automation (hooks and slash commands), optional early review, and GitHub PRs.
Apps are **not deployed to any cloud** (see [ADR-001](decisions/ADR-001-local-docker-only.md)).
Validation is two-layered: local `/ship` runs the pre-push gate against the live Docker
stack, and GitHub Actions runs lint + unit tests + build on every PR (see
[ADR-009](decisions/ADR-009-github-actions-ci.md)). E2E stays local.

---

## Quick Overview

| Phase | What Happens | Who/What | Manual or Auto? |
|---|---|---|---|
| **Write Code** | Developer writes code | Human | Manual |
| **Auto Checks** | Format, lint, compose validation | Claude Code hooks | Automatic |
| **Early Review** | Developer optionally checks quality | `/self-review` command | Manual (optional) |
| **Security Check** | Developer optionally scans for vulnerabilities | `/security-review` command | Manual (optional) |
| **Ship** | Full pipeline — doc check → reviews → build → commit → push → PR | `/ship` command | Manual (triggers orchestration) |
| **Merge** | Human code review on GitHub | GitHub | Manual |
| **Cleanup** | Checkout main, pull, delete branch | `/done` command | Manual |

---

## Automated Hooks (Always Running)

These Claude Code hooks run automatically in the background — no action required.

### `.claude/hooks/pre_bash_guard.sh`
- **When:** Before any terminal command executes
- **What it does:** Blocks dangerous commands (e.g., `rm -rf /`, `docker compose down -v`) and `.env` reads and writes
- **Why:** Prevents accidental data loss and secret exposure

### `.claude/hooks/post_format.sh`
- **When:** After a file is saved (if it's Python, JS/TS, or JSON)
- **What it does:** Auto-formats code to project standards
- **Why:** Keeps code style consistent without manual intervention

### `.claude/hooks/post_compose_validate.sh`
- **When:** After `docker-compose.yml` is edited
- **What it does:** Validates YAML syntax and ARM64 compatibility
- **Why:** Catches configuration errors early before containers start

---

## Manual Commands

These are slash commands developers invoke explicitly.

### Development Commands

| Command | Purpose | When to Run |
|---|---|---|
| `/test` | Run tests for current app | After writing tests, before shipping |
| `/lint` | Run linting and formatting checks | Optional, for manual validation |
| `/build` | Run production build | To verify build succeeds locally |
| `/logs` | Tail live container logs | For debugging container issues |

### Review Commands (Optional Early Feedback)

| Command | Purpose | When to Run |
|---|---|---|
| `/self-review` | Query MCP docs → analyze code against best practices → auto-fix issues | Right after writing code, catch issues early |
| `/security-review` | Scan for secrets, injection, auth gaps, exposed internals → auto-fix | Before `/ship`, extra peace of mind |

**Note:** These are *optional* because `/ship` will run both automatically. Use them for iterative feedback during development.

### Mandatory Workflow Commands

| Command | Purpose | When to Run |
|---|---|---|
| `/ship` | **Full pipeline:** doc check → `/self-review` → `/security-review` → lint → build → **every app's tests (backend + frontend unit + Playwright E2E)** → commit → push → open PR | When ready to submit code for review |
| `/done` | Checkout main, pull latest, delete feature branch | After PR is merged |

---

## The `/ship` Pipeline (Orchestrated Automation)

When you run `/ship`, Claude Code executes this entire sequence:

```
1. Pre-Ship Documentation Check
   ├─ CLAUDE.md is current (reflects decisions)
   ├─ PLAN.md is updated (progress marked)
   ├─ Relevant .claude/rules/*.md are current
   ├─ README.md phase table is accurate
   ├─ docs/ is up-to-date (architecture, tech, decisions)
   └─ file names match `docs/tech/file-naming-convention.md`

2. Code Quality Review (/self-review)
   ├─ Query MCP docs for framework/library standards
   ├─ Analyze code against project conventions
   ├─ Identify issues
   └─ Auto-fix where possible

3. Security Review (/security-review)
   ├─ Scan for exposed secrets/tokens
   ├─ Check for injection vulnerabilities
   ├─ Validate auth/ownership checks
   ├─ Identify exposed internals
   └─ Auto-fix where possible

4. Lint & Format
   └─ Run linting checks

5. Production Build
   └─ Run full build, verify success

6. Tests (every app — not just the changed one)
   ├─ Backend: pytest / mvn / pnpm test for each app's backend
   ├─ Frontend unit: Vitest for each app's frontend
   └─ Frontend E2E: Playwright for each app with frontend/e2e/ — requires live stack

7. Git Workflow
   ├─ Create/update commit with conventional message
   ├─ Push to origin
   └─ Open pull request (with summary)

8. PR Created
   └─ Ready for human review or auto-merge
```

**Key Point:** Everything runs in sequence. If any step fails, the pipeline stops and reports the issue.

---

## Typical Developer Workflows

### Workflow A: Iterative (Recommended for Complex Changes)

```bash
# 1. Write code
# ... (save file, post_format runs automatically)

# 2. Early review (optional but recommended)
/self-review
# → Claude Code reviews, shows issues, auto-fixes some
# → Fix remaining issues manually

# 3. Security check (optional)
/security-review
# → Claude Code scans, auto-fixes simple issues
# → Fix remaining issues manually

# 4. Ready to ship
/ship
# → Full pipeline runs
# → If passes: PR is created
# → If fails: fix and try /ship again

# 5. After merge
/done
# → Cleanup: main branch synced, feature branch deleted
```

### Workflow B: Direct Ship (Fast Track)

```bash
# 1. Write code
# ... (save file, post_format runs automatically)

# 2. Ready to ship immediately
/ship
# → Full pipeline runs (includes /self-review + /security-review)
# → If passes: PR is created
# → If fails: fix and try /ship again

# 3. After merge
/done
```

### Workflow C: Verification Only (Local Testing)

```bash
# 1. Write code
# ... (save file, post_format runs automatically)

# 2. Verify locally (optional)
/test
/lint
/build

# 3. When satisfied
/ship
# → Full pipeline runs
# → If passes: PR is created

# 4. After merge
/done
```

---

## Best Practices

### ✅ Do This

- **Use `/self-review` early** — catch issues while you're still in context
- **Use `/security-review` before shipping** — security issues block PRs
- **Always use `/ship`** — never commit directly to `main` or push without it
- **Update docs with code** — `/ship` checks this before creating PR
- **Use `/done` after merge** — keeps branches clean
- **Read hook error messages** — `.claude/hooks/pre_bash_guard.sh` is trying to save you from disasters

### ❌ Don't Do This

- **Commit directly to `main`** — branch + PR always
- **Push without `/ship`** — reviews and builds aren't automated
- **Ignore hook blocks** — if `.claude/hooks/pre_bash_guard.sh` stops you, you probably want it to
- **Skip security review** — assume vulnerabilities might exist
- **Let docs get stale** — `/ship` will fail the doc check and force you to update anyway

---

## Troubleshooting

### `/ship` Fails at Doc Check

**Problem:** "CLAUDE.md is not current"

**Solution:** 
1. Update `CLAUDE.md` with any new decisions/conventions
2. Run `/ship` again

### `/self-review` Finds Issues But Won't Auto-Fix

**Problem:** Code quality issues remain after `/self-review`

**Solution:**
1. Read the detailed issue report
2. Fix manually or request Claude Code to fix
3. Run `/self-review` again

### `/security-review` Finds Exposed Secrets

**Problem:** API keys or tokens detected in code

**Solution:**
1. **NEVER commit secrets** — use `.env.example` instead
2. Remove from code immediately
3. Run `/security-review` again
4. Never push — run `/ship` will fail

### Build Fails in `/ship`

**Problem:** Production build step fails

**Solution:**
1. Run `/build` locally to see detailed errors
2. Fix locally
3. Run `/ship` again

### Can't Run `/done` (Branch Still Exists)

**Problem:** `/done` reports the local branch couldn't be deleted.

**Cause:** `/done` uses safe-delete (`git branch -d`), which refuses if the branch has commits not merged into `main`. This usually means the PR isn't actually merged yet, or local commits were added after the PR merged.

**Solution:**
1. Confirm the PR is merged on GitHub: `gh pr view --json state`
2. Fetch and review unmerged commits: `git fetch origin && git log <branch> ^origin/main`
3. If those commits are safe to discard, force-delete: `git branch -D <branch>` then `git push origin --delete <branch>`
4. If unsure, leave the branch in place and investigate before discarding

---

## Automation scope (local only)

Per [ADR-001](decisions/ADR-001-local-docker-only.md), everything runs on the developer
machine — no Jenkins, GitHub Actions deploy pipeline, or cloud CI/CD.

| Layer | What runs | Where |
| --- | --- | --- |
| Hooks | Format, compose validation, bash guard | Claude Code (on save / before commands) |
| Slash commands | `/self-review`, `/security-review`, `/ship`, `/test`, `/lint`, `/build` | Claude Code + local toolchains |
| Runtime | Containers, healthchecks, log volumes | Docker Compose (when `docker-compose.yml` exists) |
| Merge gate | Human PR review | GitHub |

`/ship` is the intended pre-merge checklist; it does not replace human review on GitHub.

---

## Phase-Based Workflow

Each phase has a hard checkpoint. Before advancing:

1. **Complete all tasks in `PLAN.md`** for current phase
2. **Run `/ship`** on final code
3. **Merge PR**
4. **Run `/done`** to clean up
5. **Verify containers healthy:** `docker compose ps`
6. **Proceed to next phase**

See `PLAN.md` for current phase status and task list.

---

## References

- **Project rules:** [`.claude/rules/workflow.md`](../.claude/rules/workflow.md)
- **File naming:** [`docs/tech/file-naming-convention.md`](tech/file-naming-convention.md)
- **Slash commands:** [`CLAUDE.md`](../CLAUDE.md)
- **Build checkpoints:** [`PLAN.md`](../PLAN.md)
- **Architecture:** [`docs/architecture/system-overview.md`](architecture/system-overview.md)
