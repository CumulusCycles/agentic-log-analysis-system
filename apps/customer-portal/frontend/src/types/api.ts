// Hand-authored TS mirror of the SDA schemas Customer Portal consumes.
// Update by hand when shared-data-api/src/shared_data_api/schemas.py changes.

export interface LoginRequest {
  username: string;
  password: string;
}

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

export interface ApiError {
  detail: string;
}

export interface JwtClaims {
  iss: string;
  aud: string;
  user_id: string;
  role: string;
  app: string;
  iat: number;
  exp: number;
}
