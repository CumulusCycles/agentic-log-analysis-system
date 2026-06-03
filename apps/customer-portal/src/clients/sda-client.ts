import axios, { type AxiosInstance } from "axios";

import type { Config } from "../config.js";

/**
 * Thin HTTP client around the Shared Data API.
 *
 * Holds a single axios instance for the lifetime of the Customer Portal
 * process. The `X-API-Key` header is set once at construction so every
 * outgoing request includes it — per ADR-006 §1 the key is required on
 * every SDA call, including `/auth/login`.
 */
export class SharedDataAPIClient {
  private readonly http: AxiosInstance;

  constructor(cfg: Config, timeoutMs = 10_000) {
    this.http = axios.create({
      baseURL: cfg.SHARED_DATA_API_BASE_URL,
      timeout: timeoutMs,
      headers: { "X-API-Key": cfg.SHARED_DATA_API_KEY_CUSTOMER_PORTAL },
    });
  }

  async login(username: string, password: string): Promise<unknown> {
    const r = await this.http.post("/auth/login", { username, password });
    return r.data;
  }

  async getUser(userId: string, bearer: string): Promise<unknown> {
    const r = await this.http.get(`/users/${encodeURIComponent(userId)}`, {
      headers: { Authorization: `Bearer ${bearer}` },
    });
    return r.data;
  }

  async getPolicies(customerId: string, bearer: string): Promise<unknown> {
    const r = await this.http.get("/policies", {
      params: { customer_id: customerId },
      headers: { Authorization: `Bearer ${bearer}` },
    });
    return r.data;
  }

  async getClaims(customerId: string, bearer: string): Promise<unknown> {
    const r = await this.http.get("/claims", {
      params: { customer_id: customerId },
      headers: { Authorization: `Bearer ${bearer}` },
    });
    return r.data;
  }
}
