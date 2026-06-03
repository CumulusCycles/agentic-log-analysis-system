import { existsSync, statSync } from "node:fs";
import path from "node:path";

import type { Request, Response } from "express";

/**
 * SPA static-file fallback hardened against path traversal.
 *
 * Mirrors FNOL's pattern in `apps/fnol/src/fnol/main.py:spa_fallback`. For
 * any GET that didn't match an API route or `/assets/*`, attempt to serve
 * the requested file from `distDir` if it exists and lives inside `distDir`
 * (block `../../etc/passwd` and URL-encoded variants). Otherwise fall back
 * to `index.html` so React Router can resolve the client-side route.
 */
export function spaFallback(distDir: string) {
  const distResolved = path.resolve(distDir);
  const indexHtml = path.join(distResolved, "index.html");
  const hasIndex = existsSync(indexHtml);

  return function (req: Request, res: Response): void {
    const requested = req.path.replace(/^\/+/, "");

    if (requested) {
      let candidate: string;
      try {
        candidate = path.resolve(distResolved, decodeURIComponent(requested));
      } catch {
        // Malformed URI — fall through to index.html.
        candidate = "";
      }
      const inside =
        candidate === distResolved ||
        candidate.startsWith(distResolved + path.sep);
      if (
        candidate &&
        inside &&
        existsSync(candidate) &&
        statSync(candidate).isFile()
      ) {
        res.sendFile(candidate);
        return;
      }
    }

    if (hasIndex) {
      res.sendFile(indexHtml);
      return;
    }

    res.status(404).json({ detail: "Not Found" });
  };
}
