import { buildApp } from "./app.js";
import { loadConfig } from "./config.js";
import { makeLogger } from "./logger.js";

function main(): void {
  const cfg = loadConfig();
  const logger = makeLogger(cfg.LOG_FILE_PATH);
  const { express: app } = buildApp({ cfg, logger });

  const server = app.listen(cfg.PORT, () => {
    logger.info("startup_complete", { port: cfg.PORT });
  });

  const shutdown = (signal: string) => {
    logger.info("shutdown_started", { signal });
    server.close(() => process.exit(0));
  };
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

main();
