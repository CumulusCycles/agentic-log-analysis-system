import jwt from "jsonwebtoken";
import nock from "nock";
import { afterAll, afterEach, beforeAll } from "vitest";

import { buildApp } from "../src/app.js";
import type { Config } from "../src/config.js";
import { makeLogger } from "../src/logger.js";
import { JWT_AUDIENCE, JWT_ISSUER } from "../src/middleware/require-auth.js";

export const TEST_CONFIG: Config = {
  PORT: 0,
  JWT_SECRET: "test-secret-please-change",
  JWT_ALGORITHM: "HS256",
  SHARED_DATA_API_BASE_URL: "http://shared-data-api-test",
  SHARED_DATA_API_KEY_CUSTOMER_PORTAL: "test-cp-key",
  LOG_FILE_PATH: "/tmp/customer-portal-test.log",
  ENABLE_CHAOS: false,
};

export function buildTestApp() {
  const logger = makeLogger(TEST_CONFIG.LOG_FILE_PATH);
  // Silence test output unless something explicitly asserts on it.
  logger.silent = true;
  return buildApp({ cfg: TEST_CONFIG, logger });
}

export function makeToken(overrides: Record<string, unknown> = {}): string {
  const now = Math.floor(Date.now() / 1000);
  return jwt.sign(
    {
      iss: JWT_ISSUER,
      aud: JWT_AUDIENCE,
      user_id: "test-user-id",
      role: "customer",
      app: "customer-portal",
      iat: now,
      exp: now + 600,
      ...overrides,
    },
    TEST_CONFIG.JWT_SECRET,
    { algorithm: TEST_CONFIG.JWT_ALGORITHM as jwt.Algorithm },
  );
}

beforeAll(() => {
  nock.disableNetConnect();
  // Permit Supertest's loopback connections.
  nock.enableNetConnect((host) => /^127\.0\.0\.1/.test(host) || /^localhost/.test(host));
});

afterEach(() => {
  nock.cleanAll();
});

afterAll(() => {
  nock.enableNetConnect();
  nock.restore();
});
