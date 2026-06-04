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

## Testing

| App / Layer | Runner | Notes |
|---|---|---|
| Shared Data API (backend) | `pytest` + `pytest-asyncio` + `mongomock-motor` + `aiosqlite` + `asgi-lifespan` | 118 tests; SQLite + mongomock isolate from real DBs |
| FNOL (backend) | `pytest` + `pytest-asyncio` + `respx` + `asgi-lifespan` | 30 tests; SDA calls mocked via respx |
| FNOL (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 10 tests; mocks `fetch` via `vi.stubGlobal` |
| FNOL (frontend E2E) | Playwright 1.60 — `desktop-chromium` + `mobile-safari` (iPhone 14) projects | 5 specs × 2 viewports = 33 tests + 3 intentional skips; runs against the live stack |
| Customer Portal (backend) | Vitest 3 + Supertest + `nock` (SDA mock) + `jsonwebtoken` | 34 tests; node env; mounts each protected endpoint at its exact path so `/policies` falls through to the SPA |
| Customer Portal (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 8 tests; mocks `fetch` via `vi.stubGlobal` |
| Customer Portal (frontend E2E) | Playwright 1.60 — same `desktop-chromium` + `mobile-safari` projects | 5 specs × 2 viewports = 28 tests; runs against the live stack |
| Agent Portal (backend) | JUnit 5 + Spring Boot Test + Mockito (`@MockitoBean SdaClient`) + Spring `OutputCaptureExtension` + `MockRestServiceServer` | 33 tests; `@SpringBootTest` + `@AutoConfigureMockMvc` for controller + filter coverage; `MockMvc.forwardedUrl(...)` for SPA welcome-page checks |
| Agent Portal (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 8 tests; mocks `fetch` via `vi.stubGlobal` |
| Agent Portal (frontend E2E) | Playwright 1.60 — same `desktop-chromium` + `mobile-safari` projects | 5 specs × 2 viewports = 30 tests; runs against the live stack |
| Dashboard (backend) | `pytest` + `pytest-asyncio` + `httpx` + `asgi-lifespan` | 47 tests; standalone JWT auth + log ingestion (4 parsers, tail reader, rollup, /api/logs + /api/status); structlog stdout-only |
| Dashboard (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 16 tests across LoginPage, StatusBadge, StatusCard, Overview, LogExplorer, usePolling; mocks `fetch` via `vi.stubGlobal` |
| Dashboard (frontend E2E) | Playwright 1.60 — same `desktop-chromium` + `mobile-safari` projects | 16 specs × 2 viewports = 32 tests; runs against the live stack |
