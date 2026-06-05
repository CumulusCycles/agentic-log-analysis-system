import type { NextFunction, Request, Response } from "express";

import type { Logger } from "../logger.js";
import { getCurrentSource, normalizeSource, runWithSource } from "../source-context.js";

/**
 * Per-request middleware. Two responsibilities:
 *
 * 1. Bind `X-Source` (default `prod`) into an `AsyncLocalStorage` context
 *    that flows through every async callback in the request lifetime.
 *    The winston format and the axios SDA-client interceptor both read it
 *    so domain log events (`sda_upstream_rejected`, etc.) and outbound
 *    SDA calls inherit the original source.
 *
 * 2. Emit the `event=request` summary line at response completion. Mirrors
 *    FNOL/SDA shape so the dashboard parser can treat `caller="-"` (CP is
 *    at the edge) and `user="<jwt user_id>"` uniformly across apps.
 */
export function requestLogger(logger: Logger) {
  return function (req: Request, res: Response, next: NextFunction): void {
    const source = normalizeSource(req.headers["x-source"] as string | undefined);
    runWithSource(source, () => {
      const start = process.hrtime.bigint();
      res.on("finish", () => {
        const durationMs = Number(process.hrtime.bigint() - start) / 1_000_000;
        // `getCurrentSource()` resolves to the value bound above; passing
        // it explicitly keeps the test-shape assertions stable even if the
        // ALS context happens to be unset by the time `finish` fires.
        logger.info("request", {
          event: "request",
          caller: "-",
          source: getCurrentSource(),
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
    });
  };
}
