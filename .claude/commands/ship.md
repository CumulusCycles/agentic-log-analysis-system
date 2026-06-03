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
7. **Run tests for EVERY app, not just the changed one** — `/ship` is the gate. Skip an app's runner only if that app does not yet exist (i.e., its directory is missing). For each `apps/<app>/`:
   - Python (shared-data-api, fnol backend, log-dashboard backend): `cd apps/<app> && uv run pytest -q`
   - React unit tests (fnol frontend, customer-portal, agent-portal, dashboard frontend): `cd apps/<app>/frontend && pnpm test`
   - **Playwright E2E (any app with `apps/<app>/frontend/e2e/`)**: requires the live stack — confirm `docker compose ps` shows the relevant containers `(healthy)`, then `cd apps/<app>/frontend && pnpm exec playwright test --reporter=line`. If the stack is down, surface that and ask before bringing it up.
   - Java (agent-portal backend): `./mvnw test`
   - **Stop on first failure** and fix before continuing. The point of /ship's gate is no surprises.
8. **Delegate git operations to `git-agent`** (steps 9–14):
9. Stage changed files: `git add <specific files>`
10. Analyze diff and propose a conventional commit message
11. Wait for approval, then commit
12. Push branch: `git push origin <branch>`
13. Open PR: `gh pr create --title "<title>" --body "<description>"`
14. Report the PR URL
