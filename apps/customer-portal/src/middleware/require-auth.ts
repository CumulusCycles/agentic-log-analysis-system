import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";

import type { Config } from "../config.js";
import type { Logger } from "../logger.js";

/**
 * Shared JWT constants — MUST stay in sync with SDA's
 * `apps/shared-data-api/src/shared_data_api/auth/jwt.py` and FNOL's
 * `apps/fnol/src/fnol/auth/jwt.py`. See ADR-006.
 */
export const JWT_ISSUER = "shared-data-api";
export const JWT_AUDIENCE = "agentic-log-analysis-insurance-apps";

export interface JwtClaims {
  iss: string;
  aud: string;
  user_id: string;
  role: string;
  app: string;
  iat: number;
  exp: number;
}

export function requireAuth(cfg: Config, logger: Logger) {
  return function (req: Request, res: Response, next: NextFunction): void {
    const header = req.header("authorization") ?? "";
    if (!/^bearer /i.test(header)) {
      res.status(401).json({ detail: "missing bearer token" });
      return;
    }
    const token = header.slice(7).trim();
    try {
      const claims = jwt.verify(token, cfg.JWT_SECRET, {
        algorithms: [cfg.JWT_ALGORITHM as jwt.Algorithm],
        issuer: JWT_ISSUER,
        audience: JWT_AUDIENCE,
      }) as JwtClaims;
      res.locals.userId = claims.user_id;
      res.locals.userRole = claims.role;
      res.locals.bearer = token;
      next();
    } catch (err) {
      logger.info("jwt_decode_failed", {
        reason: err instanceof Error ? err.message : String(err),
      });
      res.status(401).json({ detail: "invalid token" });
    }
  };
}
