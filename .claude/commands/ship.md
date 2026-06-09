# /ship

Lint, build, commit, push, and open a PR in one shot.

## Steps
1. **Tool-enforcement audit** — run `.claude/hooks/ship_audit.sh`. Fails closed if any tool `/ship` or `/lint` prescribes is not bound in CI. No `--skip` flag by design (per `feedback_dormant_lint_tools`). Fix the gap and rerun; do NOT proceed past this step on failure. This catches the dormant-gate class of drift that produced PRs #29 (211 AP checkstyle violations) and #30 (Node `format:check` listed in `/ship` but not declared by any package).
2. **Pre-ship doc check** — verify before touching git:
   - `CLAUDE.md` reflects any new decisions from this session
   - `PLAN.md` is current — mark completed `✅`, in-progress `🔄`
   - Relevant `.claude/rules/*.md` files are current
   - `README.md` phase table is accurate
   - `docs/` reflects any architecture or tech decisions
   - New and renamed files follow `docs/tech/file-naming-convention.md` (enforced via `.claude/rules/file-naming.md`)
3. **Self-review** — run `/self-review`: query MCP docs, review diff against best practices, fix all issues
4. **Security review** — run `/security-review`: scan for secrets, injection, auth gaps, exposed internals, fix all issues
5. **Multi-agent local review for high-stakes PRs — iterate until clean.** If the local branch diff vs `main` touches any of:
   - `apps/*/middleware/` — cross-cutting request-handling code
   - `apps/shared-data-api/**` — SDA is the auth boundary + sole data layer for the three SDA-consuming apps (FNOL, CP, AP); any change can cascade across them. The dashboard reads log volumes only and is independent (ADR-005, ADR-006).
   - `dashboard/src/log_dashboard/agent/` — LangGraph topology + tools
   - `dashboard/src/log_dashboard/ingest/vectorstore.py` — credential redaction + embedder boundary
   - `docker-compose.yml` — shared infra contract
   - `.env.example` — config-shape changes
   - `docs/decisions/ADR-*.md` — architectural decisions
   - more than 20 files — size heuristic for "this PR is doing a lot"

   ...then enter the **review-fix loop**:

   1. Commit any uncommitted work locally (don't push).
   2. Run `/local-review` (no args) — reviews `git diff main...HEAD`.
   3. Triage findings with the operator. Fix Critical + High in place. Push back on or defer Medium/Low with explicit rationale.
   4. Commit the fixes locally (don't push).
   5. Re-run `/local-review`. The same multi-agent fleet now sees the fix commits as part of the diff and will surface any new issues introduced.
   6. Loop until the review reports **no Critical or High findings** — neither new ones introduced by the fix commits NOR pre-existing ones that were deferred but later re-rated. Medium/Low findings may remain unaddressed only with explicit operator agreement on the triage call.

   Only when the loop converges do you proceed to step 6 (lint). This catches the class of issue `/self-review` is structurally too narrow to find — design + correctness + test-coverage gaps that need a multi-angle read. Skips for trivial PRs (doc tweaks, lockfile bumps, single-file fixes that don't match the heuristic). Iterating BEFORE the push avoids the force-push churn and the embarrassment of a post-PR-open review finding a problem. `/ultrareview <PR#>` remains the after-/ship option for cases where you want the independent cloud reviewer with sandbox reproduction — but it's a second opinion, not the primary gate. See `feedback_local_review_before_push` memory for the workflow rationale.
6. Identify which app or area was changed (still relevant for the lint + build steps below)
7. Run lint for the changed app:
   - Python: `uv run ruff check . && uv run black --check .`
   - Node: `pnpm lint && pnpm format:check`
   - Java: `./mvnw checkstyle:check`
8. Run build for the changed app:
   - Python: `uv sync && uv run mypy .`
   - Node/React: `pnpm typecheck && pnpm build`
   - Java: `./mvnw package -DskipTests`
   - Container build is NOT run here — run `/build` manually if Dockerfile changes are part of this ship
9. **Run tests — scoped to the change set.** Two parts: unit tests for changed apps; E2E for changed apps *plus* every app when shared infra is touched.

   **9a. Determine scope from the diff:**
   - **Changed apps** — list every `apps/<name>/` path with modifications in the diff. Multiple apps may be in scope at once.
   - **Shared-contract changes** — does the diff touch any of: `apps/shared-data-api/**`, `docker-compose.yml`, `.env.example`, `.claude/rules/apps.md`? If yes, every consumer is in E2E scope.

   **9b. Unit tests — only for changed apps.** Unit tests are isolated (each app mocks its SDA collaborator at the HTTP boundary), so a change in one app cannot break another app's unit tests. The four supporting apps live under `apps/<app>/`; the dashboard lives at `dashboard/` (top-level, not under `apps/`). For each changed area:
   - Python — supporting apps: `cd apps/<app> && uv run pytest -q` (`shared-data-api`, `fnol`)
   - Python — dashboard backend: `cd dashboard && uv run pytest -q`
   - React unit tests — supporting apps: `cd apps/<app>/frontend && pnpm test` (`fnol`, `customer-portal`, `agent-portal`)
   - React unit tests — dashboard frontend: `cd dashboard/frontend && pnpm test`
   - Java — agent-portal backend: `cd apps/agent-portal && ./mvnw test`

   **9c. E2E tests — our cross-app integration coverage.** Playwright drives each app's UI against the *live* SDA + DB stack, so the E2E suite for an app exercises that app's full integration with SDA. Scope:
   - **Default:** run E2E only for changed apps' `frontend/e2e/` directory (`apps/<app>/frontend/e2e/` for supporting apps; `dashboard/frontend/e2e/` for the dashboard).
   - **If 9a flagged shared-contract changes:** run E2E for *every* app with an `e2e/` directory. SDA / compose / shared-rule changes can break every consumer — this is the integration sweep.
   - Requires the live stack — confirm `docker compose ps` shows the relevant containers `(healthy)`. If the stack is down, surface that and ask before bringing it up.
   - Supporting apps: `cd apps/<app>/frontend && pnpm exec playwright test --reporter=line`
   - Dashboard: `cd dashboard/frontend && pnpm exec playwright test --reporter=line`

   **Stop on first failure** and fix before continuing. The point of /ship's gate is no surprises.
10. **Delegate git operations to `git-agent`** (steps 11–16):
11. Stage changed files: `git add <specific files>`
12. Analyze diff and propose a conventional commit message
13. Wait for approval, then commit
14. Push branch: `git push origin <branch>`
15. Open PR: `gh pr create --title "<title>" --body "<description>"`
16. Report the PR URL

## After `/ship` opens the PR

For **high-stakes PRs** (cross-cutting middleware, LLM/LangGraph code, the agitator, anything in Phase 7e), the operator should invoke `/ultrareview <PR#>` — Claude Code's multi-agent cloud review, referenced in `.claude/rules/workflow.md` as **agentreviewer**. User-triggered only; Claude cannot launch it. See `docs/development-workflow.md` for the model preference, pre-flight checks, and finding-triage workflow.
