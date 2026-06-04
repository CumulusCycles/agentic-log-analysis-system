import type { ErrorRequestHandler } from "express";

import { AppError } from "../errors.js";
import type { Logger } from "../logger.js";

/**
 * Central error middleware. Mounted as the LAST middleware in app.ts.
 *
 * In PR 1 (Phase 6.5) the per-route try/catch wrappers in routers/* still
 * translate SdaError via `sdaErrorToHttp` themselves, so this middleware
 * primarily catches what those don't:
 *   - express.json() body-parse failures → 400
 *   - any plain Error thrown by handler code → generic 500 (with stack logged)
 * PR 3 (Express 5 upgrade) removes the per-route try/catch and routes every
 * thrown SDA error through this handler.
 */
export function errorHandler(logger: Logger): ErrorRequestHandler {
  return (err, req, res, _next) => {
    if (err instanceof AppError) {
      res.status(err.status).json({ detail: err.detail });
      return;
    }
    if (err instanceof SyntaxError) {
      // express.json() throws SyntaxError on unparseable bodies. We do not
      // surface a real SyntaxError thrown by handler code differently here —
      // routes shouldn't throw SyntaxError from working code anyway.
      res.status(400).json({ detail: "malformed request body" });
      return;
    }
    logger.error("unhandled_error", {
      event: "unhandled_error",
      error_class:
        (err as { constructor?: { name?: string } })?.constructor?.name ??
        "Unknown",
      error_message: (err as { message?: string })?.message,
      method: req.method,
      path: req.originalUrl.split("?")[0],
      stack: (err as { stack?: string })?.stack,
    });
    res.status(500).json({ detail: "internal server error" });
  };
}
