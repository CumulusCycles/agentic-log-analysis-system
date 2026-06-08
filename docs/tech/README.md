# Tech Reference

Long-form technology references — stack choices, logging strategy + event
catalog, data model, and naming conventions. The companion to
[`../../.claude/rules/`](../../.claude/rules/), which carries the same
information in compact runtime form for Claude Code; this directory is the
canonical long-form reference for human developers. When the two disagree,
these documents govern.

## Files

| File | Covers |
|---|---|
| [`tech-stack.md`](tech-stack.md) | Per-app language, framework, database driver, AI/ML stack, testing approach, and lint/format tooling |
| [`logging-strategy.md`](logging-strategy.md) | Philosophy (each app logs in its native format — no normalization at write time), per-stack log formats (structlog / Winston / Logback), volume mount paths, and the `X-Source` header convention |
| [`log-events.md`](log-events.md) | Authoritative catalog of every structured log event emitted by the four apps — event name, source file, fields, and trigger. Used by the dashboard's parser and agent |
| [`data-model.md`](data-model.md) | Mongo + Postgres schemas, claim-status enum, seed counts, and the Alembic-based schema-evolution workflow (post-PR-#6) |
| [`file-naming-convention.md`](file-naming-convention.md) | File and path naming rules for the whole repo — kebab-case / snake_case / PascalCase per location |
