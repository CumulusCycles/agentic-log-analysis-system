import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

import winston from "winston";

import { getCurrentSource } from "./source-context.js";

export type Logger = winston.Logger;

/**
 * Format that augments every log event with `source` read from the request
 * `AsyncLocalStorage`. Domain events (`sda_upstream_rejected`, etc.) emitted
 * during the request lifetime inherit the inbound `X-Source` automatically.
 * Events emitted outside a request context (startup, shutdown) get the
 * default `prod` fallback.
 *
 * If the caller already passed `source` in the meta object (e.g. the
 * `requestLogger` middleware explicitly emits `source: getCurrentSource()`),
 * we don't override — explicit beats inferred.
 */
const injectSource = winston.format((info) => {
  if (info.source === undefined) {
    info.source = getCurrentSource();
  }
  return info;
});

export function makeLogger(logFilePath: string): Logger {
  const transports: winston.transport[] = [new winston.transports.Console()];

  try {
    mkdirSync(dirname(logFilePath), { recursive: true });
    transports.push(
      new winston.transports.File({
        filename: logFilePath,
        maxsize: 10 * 1024 * 1024,
        maxFiles: 5,
      }),
    );
  } catch {
    // Log volume not mounted (e.g. local tests) — stdout is sufficient.
  }

  return winston.createLogger({
    level: "info",
    format: winston.format.combine(
      winston.format.timestamp(),
      winston.format.errors({ stack: true }),
      injectSource(),
      winston.format.json(),
    ),
    defaultMeta: { service: "customer-portal" },
    transports,
  });
}
