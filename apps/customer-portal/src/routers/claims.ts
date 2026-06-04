import { Router } from "express";

import type { SharedDataAPIClient } from "../clients/sda-client.js";
import type { Logger } from "../logger.js";

export function claimsRouter(sda: SharedDataAPIClient, logger: Logger): Router {
  const router = Router();

  router.get("/", async (_req, res) => {
    const userId = res.locals.userId as string;
    const bearer = res.locals.bearer as string;
    const claims = await sda.getClaims(userId, bearer);
    logger.info("claims_fetched", {
      event: "claims_fetched",
      user_id: userId,
      count: claims.length,
    });
    res.json(claims);
  });

  return router;
}
