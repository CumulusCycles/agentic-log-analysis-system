# /test

Run tests for the current app, or for every app (matching `/ship`'s test gate).

## Usage

| Invocation | Behavior |
|---|---|
| `/test` (no args) | Run tests for the app in focus (the app whose files I most recently edited). If unclear, ask. |
| `/test all` | Run every app's test suite — same scope as `/ship` step 7. |
| `/test <app>` | Run a single app explicitly (e.g., `/test fnol`, `/test shared-data-api`). |

## Per-app commands

### Shared Data API (`apps/shared-data-api/`)
```bash
cd apps/shared-data-api && uv run pytest -v
```

### FNOL (`apps/fnol/`)
```bash
# Backend (pytest)
cd apps/fnol && uv run pytest -v

# Frontend unit (Vitest)
cd apps/fnol/frontend && pnpm exec vitest run

# Frontend E2E (Playwright) — requires the live stack
cd apps/fnol/frontend && pnpm exec playwright test --reporter=line
```

### Customer Portal (`apps/customer-portal/`) — Phase 5
```bash
# Backend
cd apps/customer-portal && pnpm test

# Frontend unit + E2E — same pattern as FNOL once it lands
```

### Agent Portal (`apps/agent-portal/`) — Phase 6
```bash
# Backend
cd apps/agent-portal && ./mvnw test

# Frontend unit + E2E — same pattern as FNOL once it lands
```

### Agentic Log Analysis Dashboard (`dashboard/`) — Phase 7a ✅
```bash
# Backend (standalone JWT auth, structlog stdout-only)
cd dashboard && uv run pytest -q

# Frontend unit
cd dashboard/frontend && pnpm test

# Frontend E2E (requires live stack — host port 4001)
cd dashboard/frontend && pnpm exec playwright test --reporter=line
```

## Steps

1. Determine scope (`all` / single app / focus app).
2. **Playwright pre-flight:** if the run includes any app with `frontend/e2e/`, confirm the stack is up (`docker compose ps` shows the relevant containers `(healthy)`). If down, surface that and ask whether to bring it up first.
3. Execute the commands above in order. Stop on first failure for each app's chain (backend → frontend unit → E2E).
4. Report results — pass/fail counts per layer, any failing test details, total wall-clock time.
5. If all pass, confirm ready to `/ship`.
