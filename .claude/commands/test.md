# /test

Run the test suite for the current app or all apps.

## Steps
1. Identify which app is in focus or ask if unclear
2. Run the appropriate test command:
   - Shared Data API: `uv run pytest apps/shared-data-api/tests/ -v`
   - FNOL: `uv run pytest apps/fnol/tests/ -v`
   - Customer Portal: `pnpm test` inside apps/customer-portal/
   - Agent Portal: `./mvnw test` inside apps/agent-portal/
   - Agentic Log Analysis Dashboard (backend): `uv run pytest dashboard/tests/ -v` from repo root (or `uv run pytest` inside `dashboard/`)
   - Agentic Log Analysis Dashboard (frontend): `pnpm test` inside `dashboard/frontend/`
3. Report results — pass/fail counts, any failing test details
4. If all pass, confirm ready to /ship
