import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

import winston from "winston";

export type Logger = winston.Logger;

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
      winston.format.json(),
    ),
    defaultMeta: { service: "customer-portal" },
    transports,
  });
}
