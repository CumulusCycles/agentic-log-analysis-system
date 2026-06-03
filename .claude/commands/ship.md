# /ship

Lint, build, commit, push, and open a PR in one shot.

## Steps
1. **Pre-ship doc check** — verify before touching git:
   - `CLAUDE.md` reflects any new decisions from this session
   - `PLAN.md` is current — mark completed `✅`, in-progress `🔄`
   - Relevant `.claude/rules/*.md` files are current
   - `README.md` phase table is accurate
   - `docs/` reflects any architecture or tech decisions
   - New and renamed files follow `docs/tech/file-naming-convention.md` (enforced via `.claude/rules/file-naming.md`)
2. **Self-review** — run `/self-review`: query MCP docs, review diff against best practices, fix all issues
3. **Security review** — run `/security-review`: scan for secrets, injection, auth gaps, exposed internals, fix all issues
4. Identify which app or area was changed (still relevant for the lint + build steps below)
5. Run lint for the changed app:
   - Python: `uv run ruff check . && uv run black --check .`
   - Node: `pnpm lint && pnpm format:check`
   - Java: `./mvnw checkstyle:check`
6. Run build for the changed app:
   - Python: `uv sync && uv run mypy .`
   - Node/React: `pnpm typecheck && pnpm build`
   - Java: `./mvnw package -DskipTests`
   - Container build is NOT run here — run `/build` manually if Dockerfile changes are part of this ship
7. **Run tests — scoped to the change set.** Two parts: unit tests for changed apps; E2E for changed apps *plus* every app when shared infra is touched.

   **7a. Determine scope from the diff:**
   - **Changed apps** — list every `apps/<name>/` path with modifications in the diff. Multiple apps may be in scope at once.
   - **Shared-contract changes** — does the diff touch any of: `apps/shared-data-api/**`, `docker-compose.yml`, `.env.example`, `.claude/rules/apps.md`? If yes, every consumer is in E2E scope.

   **7b. Unit tests — only for changed apps.** Unit tests are isolated (each app mocks its SDA collaborator at the HTTP boundary), so a change in one app cannot break another app's unit tests. For each changed `apps/<app>/`:
   - Python (shared-data-api, fnol backend, log-dashboard backend): `cd apps/<app> && uv run pytest -q`
   - React unit tests (fnol frontend, customer-portal, agent-portal, dashboard frontend): `cd apps/<app>/frontend && pnpm test`
   - Java (agent-portal backend): `cd apps/<app> && ./mvnw test`

   **7c. E2E tests — our cross-app integration coverage.** Playwright drives each app's UI against the *live* SDA + DB stack, so the E2E suite for an app exercises that app's full integration with SDA. Scope:
   - **Default:** run E2E only for changed apps' `apps/<app>/frontend/e2e/`.
   - **If 7a flagged shared-contract changes:** run E2E for *every* app with an `e2e/` directory. SDA / compose / shared-rule changes can break every consumer — this is the integration sweep.
   - Requires the live stack — confirm `docker compose ps` shows the relevant containers `(healthy)`. If the stack is down, surface that and ask before bringing it up.
   - `cd apps/<app>/frontend && pnpm exec playwright test --reporter=line`

   **Stop on first failure** and fix before continuing. The point of /ship's gate is no surprises.
8. **Delegate git operations to `git-agent`** (steps 9–14):
9. Stage changed files: `git add <specific files>`
10. Analyze diff and propose a conventional commit message
11. Wait for approval, then commit
12. Push branch: `git push origin <branch>`
13. Open PR: `gh pr create --title "<title>" --body "<description>"`
14. Report the PR URL
