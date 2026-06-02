# Project Rules — Docker & Infrastructure

## Core Rule
Local Docker Compose only. No cloud deployment, no AWS, no CDK, no Terraform.

---

## Docker Compose
- Single root `docker-compose.yml` orchestrates all 8 containers
- All services on bridge network: `insurance-net`
- All images specify `platform: linux/arm64` (M1 Max host)
- All credentials in `.env` — never hardcoded

## ARM64 Base Images

| Service | Runtime Image | Build Stage |
|---|---|---|
| shared-data-api | `python:3.12-slim` | — |
| fnol-app | `python:3.12-slim` | `node:22-alpine` |
| customer-portal | `node:20-alpine` | `node:22-alpine` |
| agent-portal | `eclipse-temurin:21-jdk-alpine` | `node:22-alpine` |
| log-dashboard | `python:3.12-slim` | `node:22-alpine` |
| postgres | `postgres:16-alpine` | — |
| mongodb | `mongo:7` | — |
| chroma | `chromadb/chroma:1.5.9` | — |

## Docker Desktop Settings (M1 Max, 64GB)
- Allocate: 20GB RAM, 8 CPUs minimum

## Port Assignments

| Container | Internal | Host |
|---|---|---|
| shared-data-api | 8000 | 8002 |
| fnol-app | 8000 | 8001 |
| customer-portal | 3000 | 3001 |
| agent-portal | 8080 | 8081 |
| log-dashboard | 4000 | 4001 |
| postgres | 5432 | 5433 |
| mongodb | 27017 | 27018 |
| chroma | 8000 | internal only |

## Persistent Volumes
```yaml
volumes:
  postgres-data:
  mongodb-data:
  fnol-logs:
  customer-portal-logs:
  agent-portal-logs:
  chroma-data:
```

## Healthchecks
Every container must define a Docker healthcheck.

- **Postgres:** `pg_isready -U $POSTGRES_USER`
- **MongoDB:** `mongosh --eval "db.runCommand({ping:1})"`
- **Chroma:** `curl -f http://localhost:8000/api/v1/heartbeat`
- **App containers** (`shared-data-api`, `fnol-app`, `customer-portal`, `log-dashboard`): HTTP `GET /health` — see `.claude/rules/apps.md`
- **Agent Portal:** HTTP `GET /actuator/health` — see `.claude/rules/apps.md`

`log-dashboard` has `depends_on: chroma: condition: service_healthy` — the Chroma healthcheck above must pass before the dashboard starts.

## NEVER run
```bash
docker compose down -v   # destroys all volumes
```
