# Tech Stack Reference

## Apps

| App | Backend | Frontend | DB | Package Mgr |
|---|---|---|---|---|
| Shared Data API | Python 3.12 / FastAPI | None | PostgreSQL (SQLAlchemy async) | `uv` |
| FNOL | Python 3.12 / FastAPI | React 18 + Vite + TypeScript | PostgreSQL (SQLAlchemy async) | `uv` |
| Customer Portal | Node.js 20 / Express | React 18 + Vite + TypeScript | MongoDB (Mongoose) | `pnpm` |
| Agent Portal | Java 21 / Spring Boot 3 | React 18 + Vite + TypeScript | PostgreSQL (Spring Data JPA) | Maven |
| Agentic Log Analysis Dashboard | Python 3.12 / FastAPI | React 18 + Vite + TypeScript | Chroma (vector store) | `uv` + `pnpm` |

## AI / ML

| Component | Technology |
|---|---|
| Agent framework | LangChain + LangGraph |
| LLM (analysis) | OpenAI `gpt-4o` |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector store | Chroma (persistent) |
| Observability | LangSmith |

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
| FNOL | structlog + Python logging | JSON + tracebacks |
| Customer Portal | winston | Structured JSON |
| Agent Portal | Logback | Text pattern |
