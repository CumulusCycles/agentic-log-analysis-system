import { Router } from "express";

import type { SharedDataAPIClient } from "../clients/sda-client.js";
import type { Logger } from "../logger.js";

export function profileRouter(
  sda: SharedDataAPIClient,
  logger: Logger,
): Router {
  const router = Router();

  router.get("/", async (_req, res) => {
    const userId = res.locals.userId as string;
    const bearer = res.locals.bearer as string;
    const profile = await sda.getUser(userId, bearer);
    logger.info("profile_fetched", {
      event: "profile_fetched",
      user_id: userId,
    });
    res.json(profile);
  });

  return router;
}
