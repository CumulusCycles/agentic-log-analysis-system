import { AsyncLocalStorage } from "node:async_hooks";

/**
 * Per-request `X-Source` propagation for Customer Portal.
 *
 * Mirrors the structlog-contextvars pattern used by SDA / FNOL. The request
 * middleware calls `runWithSource(source, () => next())` so every async
 * callback that fires during the request inherits the source value:
 *
 *   - the winston format reads it via `getCurrentSource()` and adds
 *     `source` to every emitted log line (request lines + domain warnings
 *     like `sda_upstream_rejected`)
 *   - the axios SDA client reads it in its request interceptor and forwards
 *     `X-Source: <value>` so SDA sees the original source
 *
 * Without ALS, only the synthesised `event=request` line would carry the
 * tag; domain warnings would silently default to `unknown` in the dashboard
 * parser regardless of the real origin. Missing-header → `unknown` per
 * ADR-011 2026-06-07 amendment; the React SPA tags `prod` explicitly.
 */
const sourceStore = new AsyncLocalStorage<{ source: string }>();

const VALID_SOURCE = /^[a-z][a-z0-9_-]*$/;

export function normalizeSource(raw: string | undefined): string {
  if (raw === undefined || raw === null) return "unknown";
  const trimmed = raw.trim().toLowerCase();
  if (!trimmed) return "unknown";
  // Defensive: reject anything that isn't a plausible source token so a
  // malicious caller can't inject arbitrary log content through the header.
  return VALID_SOURCE.test(trimmed) ? trimmed : "unknown";
}

export function runWithSource<T>(source: string, fn: () => T): T {
  return sourceStore.run({ source }, fn);
}

export function getCurrentSource(): string {
  return sourceStore.getStore()?.source ?? "unknown";
}
