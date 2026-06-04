import { Router } from "express";

import type { SharedDataAPIClient } from "../clients/sda-client.js";

export function profileRouter(sda: SharedDataAPIClient): Router {
  const router = Router();

  router.get("/", async (_req, res) => {
    const userId = res.locals.userId as string;
    const bearer = res.locals.bearer as string;
    const profile = await sda.getUser(userId, bearer);
    res.json(profile);
  });

  return router;
}
