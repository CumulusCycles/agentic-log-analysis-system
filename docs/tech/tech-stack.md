# Tech Stack Reference

## Apps

| App | Backend | Frontend | Data | Package Mgr |
|---|---|---|---|---|
| Shared Data API | Python 3.12 / FastAPI | None | PostgreSQL (SQLAlchemy async) + MongoDB (Motor) — sole owner of both | `uv` |
| FNOL | Python 3.12 / FastAPI | React 18 + Vite + TypeScript | Via Shared Data API (HTTP) — no direct DB | `uv` |
| Customer Portal | Node.js 20 / Express | React 18 + Vite + TypeScript | Via Shared Data API (HTTP, read-only) — no direct DB | `pnpm` |
| Agent Portal | Java 21 / Spring Boot 3.5 | React 18 + Vite + TypeScript | Via Shared Data API (HTTP, read-only) — no direct DB | Maven Wrapper (`mvnw` checked in) |
| Agentic Log Analysis Dashboard | Python 3.12 / FastAPI | React 18 + Vite + TypeScript | Chroma (vector store) | `uv` + `pnpm` |

## AI / ML

| Component | Technology |
|---|---|
| Agent framework | LangChain + LangGraph |
| LLM (analysis) | OpenAI `gpt-4o` |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector store | Chroma (persistent) |
| Observability | LangSmith |

## Auth & Security

See ADR-006 for the strategy. Library choices per stack:

| Concern | Library / Tech |
|---|---|
| JWT (Shared Data API, FNOL, Dashboard) | `PyJWT` |
| JWT (Customer Portal) | `jsonwebtoken` |
| JWT (Agent Portal) | `jjwt` |
| Password hashing | `bcrypt` (Python), `bcryptjs` (Node), `BCryptPasswordEncoder` (Java) |
| HTTP client (apps → Shared Data API) | `httpx` (Python — SDA, FNOL, Dashboard), `axios` (Node — Customer Portal), Spring `RestClient` + JDK `HttpClient` pinned to `HTTP_1_1` (Java — Agent Portal) |
| Config validation (Node apps) | `zod` (Customer Portal) |

## Infrastructure

| Component | Technology |
|---|---|
| Orchestration | Docker Compose |
| Relational DB | PostgreSQL 16 |
| Document DB | MongoDB 7 |
| Vector DB | Chroma |
| Host | Apple M1 Max, Docker Desktop |
| Platform | `linux/arm64` |

## Logging Libraries

| App | Library | Format |
|---|---|---|
| Shared Data API | structlog + Python logging | JSON + tracebacks |
| FNOL | structlog + Python logging | JSON + tracebacks |
| Customer Portal | winston | Structured JSON |
| Agent Portal | Logback | Text pattern |

## Frontend Tooling (all React apps)

| Concern | Technology |
|---|---|
| Bundler / dev server | Vite 6 |
| Language | TypeScript 5 (strict) |
| Styling | Tailwind CSS 3 + PostCSS + autoprefixer |
| Router | `react-router-dom` v6 |
| HTTP | `fetch` (no axios) |
| Linter | ESLint 9 (flat config) + `typescript-eslint` + `eslint-plugin-react-hooks` + `eslint-plugin-react-refresh` |

## Backend Linting

| App | Linter | Config | CI binding |
|---|---|---|---|
| Shared Data API | ruff + black | `pyproject.toml` | `ci-shared-data-api.yml` |
| FNOL | ruff + black | `pyproject.toml` | `ci-fnol.yml` |
| Customer Portal | ESLint 9 (flat config) | `eslint.config.js` | `ci-customer-portal.yml` |
| Agent Portal | maven-checkstyle-plugin 3.6.0 (pinned to checkstyle 10.20.2) | `apps/agent-portal/checkstyle.xml` — Google Java Style + project overrides (4-space indent, 120-char lines, allowedAbbreviationLength=4) | Bound to `verify` Maven phase → enforced by `ci-agent-portal.yml`'s `./mvnw -B verify` |
| Dashboard (backend) | ruff + black | `pyproject.toml` | `ci-dashboard.yml` |

## Testing

| App / Layer | Runner | Notes |
|---|---|---|
| Shared Data API (backend) | `pytest` + `pytest-asyncio` + `mongomock-motor` + `aiosqlite` + `asgi-lifespan` | 120 tests; SQLite + mongomock isolate from real DBs |
| FNOL (backend) | `pytest` + `pytest-asyncio` + `respx` + `asgi-lifespan` | 32 tests; SDA calls mocked via respx |
| FNOL (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 10 tests; mocks `fetch` via `vi.stubGlobal` |
| FNOL (frontend E2E) | Playwright 1.60 — `desktop-chromium` + `mobile-safari` (iPhone 14) projects | 5 specs × 2 viewports = 33 tests + 3 intentional skips; runs against the live stack |
| Customer Portal (backend) | Vitest 3 + Supertest + `nock` (SDA mock) + `jsonwebtoken` | 36 tests; node env; mounts each protected endpoint at its exact path so `/policies` falls through to the SPA |
| Customer Portal (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 8 tests; mocks `fetch` via `vi.stubGlobal` |
| Customer Portal (frontend E2E) | Playwright 1.60 — same `desktop-chromium` + `mobile-safari` projects | 5 specs × 2 viewports = 28 tests; runs against the live stack |
| Agent Portal (backend) | JUnit 5 + Spring Boot Test + Mockito (`@MockitoBean SdaClient`) + Spring `OutputCaptureExtension` + `MockRestServiceServer` | 35 tests; `@SpringBootTest` + `@AutoConfigureMockMvc` for controller + filter coverage; `MockMvc.forwardedUrl(...)` for SPA welcome-page checks |
| Agent Portal (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 8 tests; mocks `fetch` via `vi.stubGlobal` |
| Agent Portal (frontend E2E) | Playwright 1.60 — same `desktop-chromium` + `mobile-safari` projects | 5 specs × 2 viewports = 30 tests; runs against the live stack |
| Dashboard (backend) | `pytest` + `pytest-asyncio` + `httpx` + `asgi-lifespan` + `chromadb.Client()` (in-memory) | 85 tests; standalone JWT auth + log ingestion (4 parsers, tail reader, rollup, /api/logs + /api/status) + Phase 7d embeddings (vectorstore factory, backfill, watchdog watcher, dedup gate, dry-run mode, WARN+ERROR/source=prod ingest filter, /api/logs/search with 503 degraded mode) + ADR-011 health-path overrides explicit source; structlog stdout-only |
| Dashboard (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 20 tests across LoginPage, StatusBadge, StatusCard, Overview, LogExplorer, LogExplorer search-mode, usePolling; mocks `fetch` via `vi.stubGlobal` |
| Dashboard (frontend E2E) | Playwright 1.60 — same `desktop-chromium` + `mobile-safari` projects | 18 specs × 2 viewports = 36 tests; runs against the live stack |
