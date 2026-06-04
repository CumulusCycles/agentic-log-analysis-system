import { Router } from "express";

import type { SharedDataAPIClient } from "../clients/sda-client.js";
import type { Logger } from "../logger.js";

interface LoginBody {
  username?: unknown;
  password?: unknown;
}

export function authRouter(sda: SharedDataAPIClient, logger: Logger): Router {
  const router = Router();

  // Anonymous — CP has no users of its own; this is a pass-through to SDA.
  // The constant-time bcrypt guarantee against user enumeration lives in
  // SDA's /auth/login (see reference_constant_time_login_bcrypt memory).
  router.post("/login", async (req, res) => {
    const body = req.body as LoginBody;
    if (
      typeof body?.username !== "string" ||
      typeof body?.password !== "string"
    ) {
      res.status(422).json({ detail: "username and password are required" });
      return;
    }
    const tokenResponse = await sda.login(body.username, body.password);
    logger.info("login_proxied_success", {
      event: "login_proxied_success",
      username: body.username,
    });
    res.json(tokenResponse);
  });

  return router;
}
