import type { NextFunction, Request, Response } from "express";

import type { Config } from "../config.js";
import type { Logger } from "../logger.js";

/**
 * Chaos middleware — header-driven failure simulation gated by ENABLE_CHAOS.
 *
 * Behavior identical to the SDA / FNOL / AP chaos middleware (same directive
 * grammar, clamps, log events, response shape). Per ADR-013.
 *
 * X-Chaos: slow:<ms>      -- sleep N ms (0..60000), then continue normally
 * X-Chaos: error:<status> -- return immediate HTTP <status> (400..599)
 *
 * Stack position: mounted after requestLogger so the request log line records
 * the delayed/errored response. Mounted before route handlers + requireAuth
 * so chaos fires regardless of auth state (consistent with SDA/FNOL/AP).
 */

const MAX_SLOW_MS = 60_000;

type DirectiveKind = "slow" | "error";
type Directive = { kind: DirectiveKind; n: number };

function parseDirective(value: string): Directive | null {
  const idx = value.indexOf(":");
  if (idx < 0) return null;
  const kind = value.slice(0, idx);
  const raw = value.slice(idx + 1);
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || String(n) !== raw.trim()) return null;
  if (kind === "slow" && n >= 0 && n <= MAX_SLOW_MS) return { kind: "slow", n };
  if (kind === "error" && n >= 400 && n <= 599) return { kind: "error", n };
  return null;
}

function pathOf(req: Request): string {
  return req.originalUrl.split("?")[0];
}

export function chaos(cfg: Config, logger: Logger) {
  return async function (req: Request, res: Response, next: NextFunction): Promise<void> {
    if (!cfg.ENABLE_CHAOS) {
      next();
      return;
    }
    const header = req.headers["x-chaos"];
    const directive = typeof header === "string" ? header : "";
    if (!directive) {
      next();
      return;
    }
    const parsed = parseDirective(directive);
    if (parsed === null) {
      logger.warn("chaos_directive_invalid", {
        event: "chaos_directive_invalid",
        directive_raw: directive,
        reason: "malformed",
        method: req.method,
        path: pathOf(req),
      });
      res.status(400).json({ detail: `invalid X-Chaos directive: ${directive}` });
      return;
    }
    if (parsed.kind === "slow") {
      await new Promise<void>((resolve) => {
        setTimeout(resolve, parsed.n);
      });
      logger.warn("chaos_honored", {
        event: "chaos_honored",
        directive,
        delay_ms: parsed.n,
        method: req.method,
        path: pathOf(req),
      });
      next();
      return;
    }
    // Split level by status class so 5xx is ERROR-tier signal in Chroma
    // (PR 4c proactive scan needs it). 4xx stays WARN: a chaos-driven 418
    // is operator action, not a server failure.
    const logMethod = parsed.n >= 500 && parsed.n < 600 ? logger.error : logger.warn;
    logMethod("chaos_honored", {
      event: "chaos_honored",
      directive,
      status: parsed.n,
      method: req.method,
      path: pathOf(req),
    });
    res.status(parsed.n).json({ detail: "chaos" });
  };
}
