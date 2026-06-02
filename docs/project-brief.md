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
Backend API service for centralized customer and policy data. No UI. Used by FNOL and
Agent Portal for customer/policy lookups.
**Scope:** Customer CRUD, policy lookup endpoints.

### FNOL — First Notice of Loss (Python / FastAPI + React)
A policyholder has just been in a car accident. On their phone, possibly shaken, trying to
report the incident from the scene. Mobile-first, urgent, must be fast and forgiving.
**Scope:** Accident report form + submission confirmation.

### Customer Portal (MERN)
A policyholder at home on their laptop checking claim status, viewing active policies,
or updating their profile. Desktop-focused, self-service.
**Scope:** Policy list, claim status view, basic profile page.

### Agent Portal (Java / Spring Boot + React)
An internal claim handler reviewing the day's FNOL submissions. Assigns adjusters,
updates claim statuses. Power user interface — desktop only.
**Scope:** Claim list with status filter, claim detail with status update.

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
