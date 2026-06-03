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
