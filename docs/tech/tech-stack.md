# Tech Stack Reference

## Apps

| App | Backend | Frontend | Data | Package Mgr |
|---|---|---|---|---|
| Shared Data API | Python 3.12 / FastAPI | None | PostgreSQL (SQLAlchemy async) + MongoDB (Motor) — sole owner of both | `uv` |
| FNOL | Python 3.12 / FastAPI | React 18 + Vite + TypeScript | Via Shared Data API (HTTP) — no direct DB | `uv` |
| Customer Portal | Node.js 20 / Express | React 18 + Vite + TypeScript | Via Shared Data API (HTTP, read-only) — no direct DB | `pnpm` |
| Agent Portal | Java 21 / Spring Boot 3 | React 18 + Vite + TypeScript | Via Shared Data API (HTTP, read-only) — no direct DB | Maven |
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
| HTTP client (apps → Shared Data API) | `httpx` (Python), `axios` (Node), `RestClient` (Java) |

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
| Shared Data API (backend) | `pytest` + `pytest-asyncio` + `mongomock-motor` + `aiosqlite` + `asgi-lifespan` | 91 tests; SQLite + mongomock isolate from real DBs |
| FNOL (backend) | `pytest` + `pytest-asyncio` + `respx` + `asgi-lifespan` | 20 tests; SDA calls mocked via respx |
| FNOL (frontend unit) | Vitest 3 + jsdom + `@testing-library/react` + `@testing-library/user-event` + `@testing-library/jest-dom` | 7 tests; mocks `fetch` via `vi.stubGlobal` |
| FNOL (frontend E2E) | Playwright 1.60 — `desktop-chromium` + `mobile-safari` (iPhone 14) projects | 5 specs × 2 viewports = 33 tests + 3 intentional skips; runs against the live stack |
| Customer Portal / Agent Portal / Dashboard | Stack-equivalents (TBD per phase) | Inherits the same Tailwind / Vitest / Playwright conventions |
