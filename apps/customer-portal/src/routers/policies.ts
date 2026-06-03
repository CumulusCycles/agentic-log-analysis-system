import { Router } from "express";

import type { SharedDataAPIClient } from "../clients/sda-client.js";
import { sdaErrorToHttp } from "../errors.js";

export function policiesRouter(sda: SharedDataAPIClient): Router {
  const router = Router();

  router.get("/", async (_req, res) => {
    const userId = res.locals.userId as string;
    const bearer = res.locals.bearer as string;
    try {
      const policies = await sda.getPolicies(userId, bearer);
      res.json(policies);
    } catch (err) {
      const app = sdaErrorToHttp(err);
      res.status(app.status).json({ detail: app.detail });
    }
  });

  return router;
}
