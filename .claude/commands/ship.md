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
4. Identify which app or area was changed
5. Run lint for the affected app:
   - Python: `uv run ruff check . && uv run black --check .`
   - Node: `pnpm lint && pnpm format:check`
   - Java: `./mvnw checkstyle:check`
6. Run build for the affected app:
   - Python: `uv sync && uv run mypy .`
   - Node/React: `pnpm build`
   - Java: `./mvnw package -DskipTests`
   - Container build is NOT run here — run `/build` manually if Dockerfile changes are part of this ship
7. Run tests for the affected app:
   - Python: `uv run pytest apps/<app>/tests/ -v`
   - Node/React: `pnpm test`
   - Java: `./mvnw test`
8. **Delegate git operations to `git-agent`** (steps 9–14):
9. Stage changed files: `git add <specific files>`
10. Analyze diff and propose a conventional commit message
11. Wait for approval, then commit
12. Push branch: `git push origin <branch>`
13. Open PR: `gh pr create --title "<title>" --body "<description>"`
14. Report the PR URL
