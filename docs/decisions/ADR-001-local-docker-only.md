# ADR-001: Local Docker Only — No Cloud Deployment

**Status:** Accepted

## Decision
This project runs entirely via Docker Compose on a local M1 Mac. No AWS, CDK, Terraform, or cloud deployment of any kind.

## Rationale
The project goal is to build and demonstrate an agentic log analysis system, not to operate production infrastructure. Local Docker is sufficient, faster to iterate on, and free.

## Consequences
No CI/CD deployment pipeline. All `docker compose` commands run locally.
