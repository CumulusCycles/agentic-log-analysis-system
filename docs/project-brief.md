# Agentic Log Analysis System — Project Brief

## Background & Purpose

This project has two goals running in parallel:

1. **Build a realistic insurance application ecosystem** — four lean but solid full-stack apps
   representing a real insurance company's digital touchpoints, running locally in Docker.

2. **Build an AI-powered log management tool** — a dashboard that consolidates logs from
   the three logging apps (FNOL, Customer Portal, Agent Portal) and uses LangGraph + OpenAI
   to surface real errors, explain root causes, and proactively predict problems before
   they escalate. This is the primary deliverable.

The insurance apps exist to generate meaningful, realistic logs. The dashboard is the real product.

---

## The Four Apps & Their Personas

### Shared Data API (Python / FastAPI)
Backend API service. Sole data-access layer for the whole system — owns Mongo (`users`,
`policies` with embedded vehicles) and Postgres (`claims`, `claim_status_history`). Every
read goes through it; FNOL is the only write client. Issues JWTs for the three insurance
apps and runs the background claim-status simulator.
**Scope:** Auth, customer/policy/claim endpoints, claim-status simulator. See `docs/tech/data-model.md`.

### FNOL — First Notice of Loss (Python / FastAPI + React)
A policyholder has just been in a car accident. On their phone, possibly shaken, trying to
report the incident from the scene. Mobile-first, urgent, must be fast and forgiving.
Authenticated via JWT issued by the Shared Data API. Sole write path for claims.
**Scope:** Accident report form + submission confirmation.

### Customer Portal (Node / Express + React)
A policyholder at home on their laptop checking claim status, viewing active policies, or
viewing their profile. Desktop-focused, self-service. **Read-only** client of the Shared
Data API — authenticated via JWT.
**Scope:** Policy list, claim status view, basic profile page (read-only).

### Agent Portal (Java / Spring Boot + React)
An internal claim handler reviewing the day's FNOL submissions and assigned claims.
Power user interface — desktop only. **Read-only** client of the Shared Data API —
authenticated via JWT. Claim statuses advance through the background simulator inside the
Shared Data API, not through agent action (see ADR-007).
**Scope:** Claim list with status filter, claim detail view.

---

## Logging

The apps log exactly like any real app would — INFO for normal operations, WARN for
recoverable issues, ERROR when something actually fails. Each app's stack logs in its
native format — structlog for Python, Winston JSON for Node, Logback text for Java.
The AI layer handles the heterogeneity.

---

## Architecture Decisions

- **Polyglot stack** — Python, Node, Java, each generating structurally different logs
- **Polyglot databases** — PostgreSQL (relational) + MongoDB (document)
- **Single data-access layer** — Shared Data API is the only path to user/policy/claim data; CP and AP have no DB driver (see ADR-005)
- **Read-only by design** — Customer Portal and Agent Portal only read; FNOL is the sole write path
- **Auth on every app** — JWT for FNOL/CP/AP (issued by Shared Data API), standalone JWT for the Dashboard, per-app API keys between services (see ADR-006)
- **Background claim-status simulator** — in-process task inside Shared Data API generates plausible dynamic activity (see ADR-007)
- **No normalization at write time** — logs written natively; dashboard interprets them
- **Persistent volumes** — logs survive container crashes, accumulate across dev sessions
- **Local Docker only** — no AWS, CDK, or cloud deployment
- **Monorepo** — single repo, single root `docker-compose.yml`

---

## The Agentic Log Analysis Dashboard

**Stack:** FastAPI + React + LangChain + LangGraph + OpenAI + Chroma vector store

**Agent flow:** ingest (watchdog) → embed (Chroma) → analyze (LangGraph) → correlate → predict → respond

**UI:** Overview dashboard · Log Explorer · AI Chat · Error Detail

**Two trigger modes:**
1. On-demand: user asks a question → agent queries Chroma, returns root cause + remediation
2. Proactive: background loop runs every N minutes → surfaces anomalies automatically

---

## Dev Environment

- **Machine:** Mac Studio, Apple M1 Max, 64GB RAM
- **IDE:** VS Code + Claude Code
- **Containers:** Docker Desktop (allocate 20GB RAM, 8 CPUs)
