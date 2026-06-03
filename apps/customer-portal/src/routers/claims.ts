import { Router } from "express";

import type { SharedDataAPIClient } from "../clients/sda-client.js";
import { sdaErrorToHttp } from "../errors.js";

export function claimsRouter(sda: SharedDataAPIClient): Router {
  const router = Router();

  router.get("/", async (_req, res) => {
    const userId = res.locals.userId as string;
    const bearer = res.locals.bearer as string;
    try {
      const claims = await sda.getClaims(userId, bearer);
      res.json(claims);
    } catch (err) {
      const app = sdaErrorToHttp(err);
      res.status(app.status).json({ detail: app.detail });
    }
  });

  return router;
}
