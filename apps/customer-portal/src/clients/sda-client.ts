import axios, { AxiosError, type AxiosInstance } from "axios";

import type { Config } from "../config.js";
import { sdaErrorToHttp } from "../errors.js";
import type { Logger } from "../logger.js";
import { getCurrentSource } from "../source-context.js";

/**
 * Hand-authored TS mirror of the SDA response shapes Customer Portal consumes.
 * Update by hand when shared-data-api/src/shared_data_api/schemas.py changes.
 * Mirrors frontend/src/types/api.ts — keep in sync.
 */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserOut {
  id: string;
  username: string;
  role: string;
  display_name: string;
}

export interface VehicleOut {
  vin: string;
  make: string;
  model: string;
  year: number;
}

export interface PolicyOut {
  policy_number: string;
  customer_id: string;
  effective_date: string;
  expiration_date: string;
  coverage_type: string;
  premium_cents: number;
  vehicles: VehicleOut[];
}

export interface VehicleSnapshot {
  make: string;
  model: string;
  year: number;
}

export interface ClaimOut {
  id: string;
  policy_number: string;
  customer_id: string;
  vin: string;
  vehicle_snapshot?: VehicleSnapshot | null;
  incident_at: string;
  description?: string | null;
  current_status: string;
  assigned_adjuster_id?: string | null;
  created_at: string;
}

/**
 * Thin HTTP client around the Shared Data API.
 *
 * Holds a single axios instance for the lifetime of the Customer Portal
 * process. The `X-API-Key` header is set once at construction so every
 * outgoing request includes it — per ADR-006 §1 the key is required on
 * every SDA call, including `/auth/login`.
 *
 * Every method translates AxiosError → AppError at the boundary so callers
 * can just `throw` (or let the rejection propagate); Express 5 routes it
 * to the central error middleware. Before re-throwing, each method emits
 * either `sda_upstream_rejected` (WARN, when SDA returned a status) or
 * `sda_upstream_unreachable` (WARN, transport error). NEVER logs the
 * bearer, the API key, or any password — only target/status/parsed detail.
 */
export class SharedDataAPIClient {
  private readonly http: AxiosInstance;
  private readonly logger: Logger;

  constructor(cfg: Config, logger: Logger, timeoutMs = 10_000) {
    this.logger = logger;
    this.http = axios.create({
      baseURL: cfg.SHARED_DATA_API_BASE_URL,
      timeout: timeoutMs,
      headers: { "X-API-Key": cfg.SHARED_DATA_API_KEY_CUSTOMER_PORTAL },
    });
    // Forward the inbound request's `X-Source` so SDA tags any WARN/ERROR it
    // emits with the original source (test/synthetic/prod). Without this,
    // every CP-driven SDA call would land in SDA's logger as `source=prod`.
    this.http.interceptors.request.use((config) => {
      config.headers.set("X-Source", getCurrentSource());
      return config;
    });
  }

  private logUpstreamError(target: string, err: unknown): void {
    if (err instanceof AxiosError) {
      if (err.response) {
        const data = err.response.data as { detail?: string } | undefined;
        this.logger.warn("sda_upstream_rejected", {
          event: "sda_upstream_rejected",
          target,
          status: err.response.status,
          detail: data?.detail ?? "upstream error",
        });
        return;
      }
      this.logger.warn("sda_upstream_unreachable", {
        event: "sda_upstream_unreachable",
        target,
        error_class: err.code ?? err.name,
      });
      return;
    }
    this.logger.warn("sda_upstream_unreachable", {
      event: "sda_upstream_unreachable",
      target,
      error_class: (err as { constructor?: { name?: string } })?.constructor?.name ?? "Unknown",
    });
  }

  async login(username: string, password: string): Promise<TokenResponse> {
    const target = "/auth/login";
    try {
      const r = await this.http.post<TokenResponse>(target, {
        username,
        password,
      });
      return r.data;
    } catch (err) {
      this.logUpstreamError(target, err);
      throw sdaErrorToHttp(err);
    }
  }

  async getUser(userId: string, bearer: string): Promise<UserOut> {
    const target = `/users/${encodeURIComponent(userId)}`;
    try {
      const r = await this.http.get<UserOut>(target, {
        headers: { Authorization: `Bearer ${bearer}` },
      });
      return r.data;
    } catch (err) {
      this.logUpstreamError(target, err);
      throw sdaErrorToHttp(err);
    }
  }

  async getPolicies(customerId: string, bearer: string): Promise<PolicyOut[]> {
    const target = "/policies";
    try {
      const r = await this.http.get<PolicyOut[]>(target, {
        params: { customer_id: customerId },
        headers: { Authorization: `Bearer ${bearer}` },
      });
      return r.data;
    } catch (err) {
      this.logUpstreamError(target, err);
      throw sdaErrorToHttp(err);
    }
  }

  async getClaims(customerId: string, bearer: string): Promise<ClaimOut[]> {
    const target = "/claims";
    try {
      const r = await this.http.get<ClaimOut[]>(target, {
        params: { customer_id: customerId },
        headers: { Authorization: `Bearer ${bearer}` },
      });
      return r.data;
    } catch (err) {
      this.logUpstreamError(target, err);
      throw sdaErrorToHttp(err);
    }
  }
}
