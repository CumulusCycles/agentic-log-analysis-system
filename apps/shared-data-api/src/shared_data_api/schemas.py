from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    display_name: str


class VehicleOut(BaseModel):
    vin: str
    make: str
    model: str
    year: int


class PolicyOut(BaseModel):
    policy_number: str
    customer_id: str
    effective_date: date
    expiration_date: date
    coverage_type: str
    premium_cents: int
    vehicles: list[VehicleOut]


class ClaimCreate(BaseModel):
    policy_number: str
    customer_id: str
    vin: str
    incident_at: datetime
    description: str | None = None


class ClaimStatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor_id: str
    changed_at: datetime
    note: str | None = None


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_number: str
    customer_id: str
    vin: str
    vehicle_snapshot: dict
    incident_at: datetime
    description: str | None = None
    current_status: str
    assigned_adjuster_id: str | None = None
    created_at: datetime


class ClaimDetail(ClaimOut):
    history: list[ClaimStatusHistoryOut] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
