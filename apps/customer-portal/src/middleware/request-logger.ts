import type { NextFunction, Request, Response } from "express";

import type { Logger } from "../logger.js";

/**
 * Per-request log line — mirrors FNOL/SDA shape so the dashboard's parser
 * can treat caller="-" (CP is at the edge) and user="<jwt user_id>" the
 * same way across apps.
 */
export function requestLogger(logger: Logger) {
  return function (req: Request, res: Response, next: NextFunction): void {
    const start = process.hrtime.bigint();
    res.on("finish", () => {
      const durationMs = Number(process.hrtime.bigint() - start) / 1_000_000;
      logger.info("request", {
        event: "request",
        caller: "-",
        user: (res.locals.userId as string | undefined) ?? "-",
        method: req.method,
        // originalUrl preserves the full mount path (e.g. "/policies/me");
        // req.path would only show "/me" inside a sub-router.
        path: req.originalUrl.split("?")[0],
        status: res.statusCode,
        duration_ms: Math.round(durationMs * 100) / 100,
      });
    });
    next();
  };
}
