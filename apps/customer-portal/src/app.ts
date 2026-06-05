import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import express, { type Express } from "express";

import { SharedDataAPIClient } from "./clients/sda-client.js";
import type { Config } from "./config.js";
import type { Logger } from "./logger.js";
import { errorHandler } from "./middleware/error-handler.js";
import { requestLogger } from "./middleware/request-logger.js";
import { requireAuth } from "./middleware/require-auth.js";
import { authRouter } from "./routers/auth.js";
import { claimsRouter } from "./routers/claims.js";
import { healthRouter } from "./routers/health.js";
import { policiesRouter } from "./routers/policies.js";
import { profileRouter } from "./routers/profile.js";
import { spaFallback } from "./spa.js";

export interface BuildAppOptions {
  cfg: Config;
  logger: Logger;
  sda?: SharedDataAPIClient;
}

export interface CustomerPortalApp {
  express: Express;
  sda: SharedDataAPIClient;
}

export function buildApp({ cfg, logger, sda }: BuildAppOptions): CustomerPortalApp {
  const client = sda ?? new SharedDataAPIClient(cfg, logger);

  const app = express();
  app.disable("x-powered-by");
  app.use(express.json({ limit: "1mb" }));
  app.use(requestLogger(logger));

  // Anonymous — health probe + login proxy.
  app.use("/", healthRouter());
  app.use("/auth", authRouter(client, logger));

  // Protected — mount each handler at its exact path so paths like /policies
  // (without /me) fall through to the React SPA below instead of being
  // rejected by requireAuth as 401.
  const protect = requireAuth(cfg, logger);
  app.use("/profile/me", protect, profileRouter(client, logger));
  app.use("/policies/me", protect, policiesRouter(client, logger));
  app.use("/claims/me", protect, claimsRouter(client, logger));

  // Static React build — mounted after API routes so they take precedence.
  // dist may be missing in tests; in production it's copied in by the Dockerfile.
  const here = path.dirname(fileURLToPath(import.meta.url));
  // src/app.ts → dist/app.js at runtime; in either case `frontend/dist` sits
  // alongside the backend's working directory root.
  const distDir = path.resolve(here, "..", "frontend", "dist");
  if (existsSync(distDir)) {
    app.use("/assets", express.static(path.join(distDir, "assets"), { fallthrough: false }));
    // Express 5 / path-to-regexp 8 requires a named wildcard; "*" alone is
    // a syntax error. "/*splat" matches /policies, /xyz, /a/b/c — but NOT
    // the bare "/" root. Wrap the segment in braces ("{/*splat}") so the
    // whole match becomes optional and "/" is included.
    app.get("{/*splat}", spaFallback(distDir));
  } else {
    logger.warn("frontend_dist_missing", { expected: distDir });
  }

  // Last — error middleware must be after all routes (and after the SPA
  // fallback) so thrown errors and body-parse failures funnel through here.
  app.use(errorHandler(logger));

  return { express: app, sda: client };
}
