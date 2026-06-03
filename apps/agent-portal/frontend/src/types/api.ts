// Hand-authored TS mirror of the SDA schemas Agent Portal consumes.
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

export interface ClaimStatusHistoryOut {
  from_status: string | null;
  to_status: string;
  actor_id: string;
  changed_at: string;
  note?: string | null;
}

export interface ClaimDetail extends ClaimOut {
  history: ClaimStatusHistoryOut[];
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
