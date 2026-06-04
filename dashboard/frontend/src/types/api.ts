// Hand-authored TS mirror of the dashboard backend schemas. Update by hand
// when dashboard/src/log_dashboard/schemas.py changes.

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface AdminOut {
  username: string;
  role: string;
}

export interface ApiError {
  detail: string;
}

export interface JwtClaims {
  iss: string;
  aud: string;
  sub: string;
  role: string;
  iat: number;
  exp: number;
}
