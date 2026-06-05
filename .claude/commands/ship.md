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
5. Identify which app or area was changed (still relevant for the lint + build steps below)
6. Run lint for the changed app:
   - Python: `uv run ruff check . && uv run black --check .`
   - Node: `pnpm lint && pnpm format:check`
   - Java: `./mvnw checkstyle:check`
7. Run build for the changed app:
   - Python: `uv sync && uv run mypy .`
   - Node/React: `pnpm typecheck && pnpm build`
   - Java: `./mvnw package -DskipTests`
   - Container build is NOT run here — run `/build` manually if Dockerfile changes are part of this ship
8. **Run tests — scoped to the change set.** Two parts: unit tests for changed apps; E2E for changed apps *plus* every app when shared infra is touched.

   **8a. Determine scope from the diff:**
   - **Changed apps** — list every `apps/<name>/` path with modifications in the diff. Multiple apps may be in scope at once.
   - **Shared-contract changes** — does the diff touch any of: `apps/shared-data-api/**`, `docker-compose.yml`, `.env.example`, `.claude/rules/apps.md`? If yes, every consumer is in E2E scope.

   **8b. Unit tests — only for changed apps.** Unit tests are isolated (each app mocks its SDA collaborator at the HTTP boundary), so a change in one app cannot break another app's unit tests. For each changed `apps/<app>/`:
   - Python (shared-data-api, fnol backend, log-dashboard backend): `cd apps/<app> && uv run pytest -q`
   - React unit tests (fnol frontend, customer-portal, agent-portal, dashboard frontend): `cd apps/<app>/frontend && pnpm test`
   - Java (agent-portal backend): `cd apps/<app> && ./mvnw test`

   **8c. E2E tests — our cross-app integration coverage.** Playwright drives each app's UI against the *live* SDA + DB stack, so the E2E suite for an app exercises that app's full integration with SDA. Scope:
   - **Default:** run E2E only for changed apps' `apps/<app>/frontend/e2e/`.
   - **If 8a flagged shared-contract changes:** run E2E for *every* app with an `e2e/` directory. SDA / compose / shared-rule changes can break every consumer — this is the integration sweep.
   - Requires the live stack — confirm `docker compose ps` shows the relevant containers `(healthy)`. If the stack is down, surface that and ask before bringing it up.
   - `cd apps/<app>/frontend && pnpm exec playwright test --reporter=line`

   **Stop on first failure** and fix before continuing. The point of /ship's gate is no surprises.
9. **Delegate git operations to `git-agent`** (steps 10–15):
10. Stage changed files: `git add <specific files>`
11. Analyze diff and propose a conventional commit message
12. Wait for approval, then commit
13. Push branch: `git push origin <branch>`
14. Open PR: `gh pr create --title "<title>" --body "<description>"`
15. Report the PR URL

## After `/ship` opens the PR

For **high-stakes PRs** (cross-cutting middleware, LLM/LangGraph code, the agitator, anything in Phase 7e), the operator should invoke `/ultrareview <PR#>` — Claude Code's multi-agent cloud review, referenced in `.claude/rules/workflow.md` as **agentreviewer**. User-triggered only; Claude cannot launch it. See `docs/development-workflow.md` for the model preference, pre-flight checks, and finding-triage workflow.
