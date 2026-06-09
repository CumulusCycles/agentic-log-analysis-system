---
description: Inspect raw log volumes from Docker containers. Triggered when asked to read, debug, or verify log output directly from Docker volumes.
---

# Log Analysis Skill

## When to Use
- When asked to read or analyze logs from any app
- When debugging a container that isn't behaving correctly
- When verifying logs are being written to persistent volumes correctly

## Steps
1. Identify which app's logs to read
2. Inspect the volume: `docker run --rm -v <volume>:/data alpine ls -la /data`
3. Read recent entries: `docker run --rm -v <volume>:/data alpine tail -100 /data/<logfile>`
4. Identify log format (structlog JSON + plain tracebacks for Shared Data API + FNOL; Winston JSON for customer-portal; Logback text for agent-portal)
5. Summarize: error count, most recent errors, any patterns
6. Flag misconfigurations vs real application errors

## Log File Reference
| App | Volume | Log File |
|---|---|---|
| Shared Data API | `shared-data-api-logs` | `shared-data-api.log` |
| FNOL | `fnol-logs` | `fnol-app.log` |
| Customer Portal | `customer-portal-logs` | `customer-portal.log` |
| Agent Portal | `agent-portal-logs` | `agent-portal.log` |

Shared Data API's log volume is the richest source per ADR-005 — every line carries `caller=<app>` and `user=<id>` attribution.
