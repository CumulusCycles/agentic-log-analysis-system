import { Router } from "express";

import type { SharedDataAPIClient } from "../clients/sda-client.js";
import type { Logger } from "../logger.js";

export function policiesRouter(sda: SharedDataAPIClient, logger: Logger): Router {
  const router = Router();

  router.get("/", async (_req, res) => {
    const userId = res.locals.userId as string;
    const bearer = res.locals.bearer as string;
    const policies = await sda.getPolicies(userId, bearer);
    logger.info("policies_fetched", {
      event: "policies_fetched",
      user_id: userId,
      count: policies.length,
    });
    res.json(policies);
  });

  return router;
}
