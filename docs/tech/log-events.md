# Log Event Catalog

Enumerates every structured log event emitted by the four supporting apps. The
Phase 7 dashboard agent ingests every line written to the four log volumes;
this catalog is the authoritative inventory of WHAT each app emits, at WHICH
level, with WHICH fields, and on WHICH trigger.

For HOW each app's logger is configured (libraries, formats, volume mounts)
see [`logging-strategy.md`](./logging-strategy.md). For the binding
prohibition on logging credentials see
[`.claude/rules/logging.md`](../../.claude/rules/logging.md) §Non-Negotiable
Rules.

**Maintenance contract:** every PR that adds, removes, or renames a log
event MUST update this file in the same diff.

---

## Volume map (recap)

| App | Volume | Log file | Dashboard read path |
|---|---|---|---|
| Shared Data API | `shared-data-api-logs` | `/app/logs/shared-data-api.log` | `/mnt/logs/shared-data-api/shared-data-api.log` |
| FNOL | `fnol-logs` | `/app/logs/fnol-app.log` | `/mnt/logs/fnol/fnol-app.log` |
| Customer Portal | `customer-portal-logs` | `/app/logs/customer-portal.log` | `/mnt/logs/customer-portal/customer-portal.log` |
| Agent Portal | `agent-portal-logs` | `/app/logs/agent-portal.log` | `/mnt/logs/agent-portal/agent-portal.log` |

All four apps also log to stdout (`docker compose logs <service>`).

---

## Shared Data API — 26 events

Python `structlog` JSON. Module-level `log = get_logger(<name>)`; each event
emits a JSON line with `event`, `level`, `logger`, `timestamp`, plus the
event-specific fields below.

### ERROR

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `simulator_persistent_failure` | `simulator/claim_status.py` | `consecutive`, `message` | Simulator has failed ≥ `ALARM_THRESHOLD` consecutive ticks |
| `unhandled_exception` | `exception_handlers.py` | `caller`, `user`, `method`, `path`, `status`, `error_class`, `exc_info` | Any uncaught exception in a request (FastAPI `Exception` handler) |

### WARN

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `api_key_collision` | `middleware/api_key.py` | `apps`, `message` | Two or more apps configured with the same `X-API-Key` value (detected at middleware init) |
| `chaos_directive_invalid` | `middleware/chaos.py` | `directive_raw`, `reason`, `method`, `path` | `X-Chaos` header value did not parse as `slow:<0..60000>` or `error:<400..599>`. 400 returned. Only fires when `ENABLE_CHAOS=true`. See ADR-013 |
| `chaos_honored` | `middleware/chaos.py` | `directive`, `delay_ms` (slow) or `status` (error), `method`, `path` | Chaos middleware honored an `X-Chaos` directive. **Level varies by status** (per ADR-013 2026-06-06 amendment): logged at **ERROR** when `status ∈ [500, 599]`; at **WARN** otherwise (4xx returns + every `slow:` honor). `delay_ms` present for `slow:N`; `status` present for `error:N`. Only fires when `ENABLE_CHAOS=true`. See ADR-013 |
| `claim_validation_rejected` | `services/claims_service.py` | `rule`, plus rule-specific identifiers (`caller`, `jwt_app`, `jwt_role`, `jwt_user_id`, `policy_number`, `vin`, `payload_customer_id`, `policy_owner_customer_id`, `incident_at`, `effective_date`, `expiration_date`) | Any business-rule rejection inside `POST /claims`. `rule` ∈ {`caller_must_be_fnol`, `jwt_app_mismatch`, `role_must_be_customer`, `impersonation_blocked`, `policy_not_found`, `customer_does_not_own_policy`, `vin_not_on_policy`, `incident_in_future`, `incident_outside_policy_window`} |
| `claims_seed_skipped` | `seeds/seed.py` | `reason` | Seed routine skipped (idempotent — DB not empty) |
| `frontend_dist_missing` | `main.py` | `expected` | SPA `dist/` not present at startup (local dev or test) |
| `login_failed` | `routers/auth.py` | `username`, `reason` (`"user_not_found"` or `"bad_password"`), `caller` | `POST /auth/login` rejected. Bcrypt runs in both reasons (constant-time guarantee) |
| `mongo_connect_failed` | `db/mongo.py` | `attempt`, `error` | Retry attempt while connecting to Mongo at startup |
| `postgres_connect_failed` | `db/postgres.py` | `attempt`, `error` | Retry attempt while connecting to Postgres at startup |
| `postgres_create_all_failed` | `db/postgres.py` | `attempt`, `error` | `create_all()` retry (used in tests via conftest bypass; see ADR-008) |
| `postgres_migrate_failed` | `db/postgres.py` | `attempt`, `error`, `via` | Alembic `upgrade head` retry at startup |
| `request_validation_error` | `exception_handlers.py` | `caller`, `user`, `method`, `path`, `status`, `errors` | `RequestValidationError` 422 |
| `volume_asymmetry_detected` | `db/consistency.py` | `missing_customer_refs`, `missing_adjuster_refs`, `missing_actor_refs` | Cross-DB referential check at startup found gaps |

### INFO

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `claim_created` | `services/claims_service.py` | `claim_id`, `customer_id`, `policy_number`, `vin`, `actor_id` | `POST /claims` succeeded (after `session.refresh`) |
| `claim_fetched` | `routers/claims.py` | `claim_id`, `current_status` | `GET /claims/{id}` returned 200 |
| `http_exception` | `exception_handlers.py` | `caller`, `user`, `method`, `path`, `status`, `detail` | Any `HTTPException` (4xx response) — translated by the handler |
| `jwt_decode_failed` | `auth/jwt.py` | `reason`, `error` | PyJWT decode raised (token rejected, never echoes the token) |
| `login_success` | `routers/auth.py` | `user_id`, `username`, `role`, `app`, `caller` | `POST /auth/login` issued a JWT |
| `mongo_connected` | `db/mongo.py` | `attempt`, `database` | Mongo connection succeeded |
| `mongo_indexes_ensured` | `db/mongo.py` | — | Mongo unique indexes applied at startup |
| `mongo_seed_complete` | `seeds/seed.py` | `customers`, `agents`, `policies` | Mongo seed routine wrote initial documents |
| `policy_fetched` | `routers/policies.py` | `count` (list) or `policy_number` (single), `customer_id` | `GET /policies` or `GET /policies/{number}` returned 200 |
| `postgres_connected` | `db/postgres.py` | `attempt` | Postgres connection succeeded |
| `postgres_schema_ready` | `db/postgres.py` | `attempt`, `via` | Alembic schema migration succeeded |
| `postgres_seed_complete` | `seeds/seed.py` | `claims` | Postgres seed routine wrote initial claims |
| `request` | `middleware/request_logger.py` | `caller`, `user`, `method`, `path`, `status`, `duration_ms` | Every request — the dashboard's primary correlation source |
| `seed_run_complete` | `seeds/seed.py` | `mongo`, `postgres` | Both seed routines finished |
| `simulator_recovered` | `simulator/claim_status.py` | `after_failures` | Simulator tick succeeded after a prior failure streak |
| `startup_complete` | `main.py` | — | FastAPI lifespan finished startup |
| `status_transition` | `simulator/claim_status.py` | `caller`, `user`, `claim_id`, `from_status`, `to_status` | Simulator advanced a claim through the status machine |
| `user_fetched` | `routers/users.py` | `user_id`, `role` | `GET /users/{id}` returned 200 |
| `volume_asymmetry_check_clean` | `db/consistency.py` | — | Cross-DB referential check passed |

### EXCEPTION

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `simulator_tick_failed` | `simulator/claim_status.py` | `consecutive` | One simulator tick failed (logged with `exc_info`) — does not yet warrant `simulator_persistent_failure` |

---

## FNOL — 14 events

Python `structlog` JSON (same library setup as SDA).

### ERROR

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `unhandled_exception` | `exception_handlers.py` | `user`, `method`, `path`, `status`, `error_class`, `exc_info` | Any uncaught exception |

### WARN

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `chaos_directive_invalid` | `middleware/chaos.py` | `directive_raw`, `reason`, `method`, `path` | `X-Chaos` header value did not parse. 400 returned. Only fires when `ENABLE_CHAOS=true`. See ADR-013 |
| `chaos_honored` | `middleware/chaos.py` | `directive`, `delay_ms` (slow) or `status` (error), `method`, `path` | Chaos middleware honored an `X-Chaos` directive. **Level varies by status** (per ADR-013 2026-06-06 amendment): logged at **ERROR** when `status ∈ [500, 599]`; at **WARN** otherwise (4xx returns + every `slow:` honor). `delay_ms` present for `slow:N`; `status` present for `error:N`. Only fires when `ENABLE_CHAOS=true`. See ADR-013 |
| `frontend_dist_missing` | `main.py` | `expected` | SPA `dist/` not present at startup |
| `request_validation_error` | `exception_handlers.py` | `user`, `method`, `path`, `status`, `errors` | `RequestValidationError` 422 |
| `sda_upstream_rejected` | `clients/shared_data_api.py` | `target`, `status`, `detail` | SDA returned 4xx/5xx on an outbound call. `detail` parsed from response body — NEVER from headers (would leak Authorization / X-API-Key) |
| `sda_upstream_unreachable` | `clients/shared_data_api.py` | `target`, `error_class` | Transport-level failure (`httpx.RequestError` subclass) |
| `shared_data_api_unreachable` | `exception_handlers.py` | `user`, `method`, `path`, `status`, `error_class` | `httpx.RequestError` bubbled to the global handler (502 translated) |

### INFO

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `claim_submitted` | `routers/claims.py` | `claim_id`, `user_id`, `policy_number`, `vin` | `POST /fnol/submit` proxied to SDA returned 201 |
| `http_exception` | `exception_handlers.py` | `user`, `method`, `path`, `status`, `detail` | Any `HTTPException` (4xx) |
| `jwt_decode_failed` | `auth/jwt.py` | `reason` | PyJWT decode rejected the bearer |
| `login_proxied_success` | `routers/auth.py` | `username` | `POST /auth/login` proxied to SDA returned 200 |
| `request` | `middleware/request_logger.py` | `caller`, `user`, `method`, `path`, `status`, `duration_ms` | Every request (FNOL is the edge — `caller="-"`) |
| `startup_complete` | `main.py` | — | FastAPI lifespan finished |

---

## Customer Portal — 14 events

Node.js `winston` JSON, one object per line. Every event includes
`level`, `message`, `timestamp`, `service` (= `"customer-portal"`) by
winston default, plus the event-specific fields below. The `event` field
is included on enrichment events for parser-friendly key (winston's
`message` is the event name as well).

### ERROR

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `unhandled_exception` | `middleware/error-handler.ts` | `error_class`, `error_message`, `method`, `path`, `stack` | Any uncaught exception in a route. Renamed from `unhandled_error` in Phase 6.75 for cross-app consistency |

### WARN

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `chaos_directive_invalid` | `middleware/chaos.ts` | `directive_raw`, `reason`, `method`, `path` | `X-Chaos` header value did not parse. 400 returned. Only fires when `ENABLE_CHAOS=true`. See ADR-013 |
| `chaos_honored` | `middleware/chaos.ts` | `directive`, `delay_ms` (slow) or `status` (error), `method`, `path` | Chaos middleware honored an `X-Chaos` directive. **Level varies by status** (per ADR-013 2026-06-06 amendment): logged at **ERROR** when `status ∈ [500, 599]`; at **WARN** otherwise. Only fires when `ENABLE_CHAOS=true`. See ADR-013 |
| `frontend_dist_missing` | `app.ts` | `expected` | SPA `dist/` not present at startup |
| `sda_upstream_rejected` | `clients/sda-client.ts` | `target`, `status`, `detail` | SDA returned 4xx/5xx on an axios call. `detail` parsed from response body |
| `sda_upstream_unreachable` | `clients/sda-client.ts` | `target`, `error_class` | Transport failure (no `err.response`) |

### INFO

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `claims_fetched` | `routers/claims.ts` | `user_id`, `count` | `GET /claims/me` returned 200 |
| `jwt_decode_failed` | `middleware/require-auth.ts` | `reason` | `jsonwebtoken` rejected the bearer |
| `login_proxied_success` | `routers/auth.ts` | `username` | `POST /auth/login` proxied to SDA returned 200 |
| `policies_fetched` | `routers/policies.ts` | `user_id`, `count` | `GET /policies/me` returned 200 |
| `profile_fetched` | `routers/profile.ts` | `user_id` | `GET /profile/me` returned 200 |
| `request` | `middleware/request-logger.ts` | `caller` (= `"-"`), `user`, `method`, `path`, `status`, `duration_ms` | Every request |
| `shutdown_started` | `server.ts` | `signal` | SIGTERM/SIGINT received |
| `startup_complete` | `server.ts` | `port` | Express `listen()` callback |

---

## Agent Portal — 11 events

Java Logback text pattern: `YYYY-MM-DD HH:mm:ss.SSS LEVEL --- [thread] class : message`.
Events use SLF4J placeholder syntax (e.g., `log.info("login_proxied_success username={}", body.username())`).
The dashboard's parser tokenizes `key=value` pairs from the message.

### ERROR

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `unhandled_exception` | `web/GlobalExceptionHandler.java` | `path`, `method`, exception stack | Any uncaught exception (`@ExceptionHandler(Exception.class)`) |

### WARN

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `chaos_directive_invalid` | `chaos/ChaosFilter.java` | `directive_raw`, `reason`, `method`, `path` | `X-Chaos` header value did not parse. 400 returned. Only fires when `app.chaos.enabled=true` (i.e. `ENABLE_CHAOS=true`). See ADR-013 |
| `chaos_honored` | `chaos/ChaosFilter.java` | `directive`, `delay_ms` (slow) or `status` (error), `method`, `path` | Chaos filter honored an `X-Chaos` directive. **Level varies by status** (per ADR-013 2026-06-06 amendment): logged at **ERROR** when `status ∈ [500, 599]`; at **WARN** otherwise. Only fires when `app.chaos.enabled=true`. See ADR-013 |
| `sda_upstream_rejected` | `sda/SdaClient.java` (in `throwSda`) | `target`, `status`, `detail` | SDA returned 4xx/5xx on a `RestClient` call |
| `sda_upstream_unreachable` | `sda/SdaClient.java` (in `invoke`) | `target`, `error_class` | Spring `ResourceAccessException` (transport failure) |

### INFO

| Event | Where | Fields | Trigger |
|---|---|---|---|
| `claim_fetched` | `web/ClaimsController.java` | `claim_id`, `current_status` | `GET /api/claims/{id}` returned 200 |
| `claims_fetched` | `web/ClaimsController.java` | `count` | `GET /api/claims` returned 200 |
| `jwt_decode_failed` | `auth/JwtAuthenticationFilter.java` | `reason` | jjwt rejected the bearer |
| `login_proxied_success` | `web/AuthController.java` | `username` | `POST /api/auth/login` proxied to SDA returned 200 |
| `profile_fetched` | `web/ProfileController.java` | `user_id` | `GET /api/profile/me` returned 200 |
| `request` | `logging/RequestLoggingFilter.java` | `method`, `path`, `caller` (= `"-"`), `user`, `status`, `duration_ms` | Every request under `/api/` |

---

## Dashboard — Agitator events (PR 3)

The dashboard logs to stdout only (no log volume; per `.claude/rules/logging.md`).
These Agitator events are the only PR-3-introduced lines; they emit at INFO so
they're visible via `docker compose logs log-dashboard` but are dropped by the
default ingest gate (`DASHBOARD_INGEST_LEVELS=WARN,ERROR`) and never enter Chroma.

| Event | Producer | Fields | Meaning |
|---|---|---|---|
| `agitator_run_started` | `routers/agitator.py` | `run_id`, `scenario`, `params` | Operator clicked Run; bounded scenario task scheduled |
| `agitator_run_complete` | `routers/agitator.py` | `run_id`, `scenario`, `state` (`succeeded`/`failed`/`cancelled`), `error_class` (failed only) | Scenario task exited |
| `agitator_login_ok` | `agitator/auth.py` | `app`, `username` | Per-scenario login to FNOL/CP/AP succeeded — never logs the password or token |
| `agitator_login_failed` | `agitator/auth.py` | `app`, `reason` (`transport_error` / `non_200` / `missing_token`), `status` (when applicable), `error_class` (when applicable) | Per-scenario login failed — router converts to 502 |

---

## Cross-app conventions

- **Every request** carries `caller`, `user`, `method`, `path`, `status`,
  `duration_ms` — the dashboard's primary correlation tuple.
- **Every auth failure** uses `jwt_decode_failed` with a `reason` string
  (the decoder's error message — NEVER the token itself).
- **Every SDA-bound outbound call failure** (FNOL, CP, AP) emits one of
  `sda_upstream_rejected` (status returned) or `sda_upstream_unreachable`
  (transport failure). `target` is the SDA path the caller tried to reach;
  `detail` (when present) is parsed from the response JSON body.
- **Every uncaught exception** emits `unhandled_exception` (NOT
  `unhandled_error`) for parser consistency across Python, Node, and Java.
- **Login success** is universally `login_success` on SDA (origin) and
  `login_proxied_success` on FNOL / CP / AP (each proxies to SDA).

---

## What is NEVER logged

Binding prohibition — see [`feedback_never_log_credentials`](../../.claude/rules/logging.md):

- Passwords (plain, hashed, or any intermediate form)
- JWT secrets / signing keys
- API keys (`SHARED_DATA_API_KEY_*`)
- Bearer tokens, full JWTs, or any token segment
- DB credentials (`POSTGRES_PASSWORD`, `MONGO_INITDB_ROOT_PASSWORD`)
- LLM keys (`OPENAI_API_KEY`, `LANGSMITH_API_KEY`)
- Admin credentials
- Any other `.env` value

Identifiers (`user_id`, `username`, `policy_number`, `vin`, `claim_id`,
`caller`) and outcomes (`status`, `duration_ms`, decoder `reason` strings)
ARE safe to log. The audit baseline (zero credential leaks across all four
apps) was verified on 2026-06-04 and is re-checked on every PR that
touches logging.
