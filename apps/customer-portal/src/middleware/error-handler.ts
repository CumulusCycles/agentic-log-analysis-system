import type { ErrorRequestHandler } from "express";

import { AppError } from "../errors.js";
import type { Logger } from "../logger.js";

/**
 * Central error middleware. Mounted as the LAST middleware in app.ts.
 *
 * Handles:
 *   - AppError (including SDA upstream errors translated by sda-client) → status + detail verbatim
 *   - SyntaxError from express.json() body parsing → 400 "malformed request body"
 *   - any plain Error thrown by handler code → generic 500 (with stack logged, no leak)
 *
 * Express 5's promise-aware router routes thrown async rejections here
 * automatically — no per-route try/catch wrappers needed.
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
    logger.error("unhandled_exception", {
      event: "unhandled_exception",
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
