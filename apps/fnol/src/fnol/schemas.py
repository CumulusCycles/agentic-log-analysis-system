"""Pydantic models mirroring the subset of SDA schemas FNOL exchanges.

Update by hand when SDA schemas change. See plan note in
`docs/tech/data-model.md` for the contract.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ClaimCreate(BaseModel):
    customer_id: str
    policy_number: str
    vin: str
    incident_at: datetime
    description: str | None = None


class ClaimOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    policy_number: str
    customer_id: str
    vin: str
    incident_at: datetime
    description: str | None = None
    current_status: str
    assigned_adjuster_id: str | None = None
    created_at: datetime


class ClaimHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_status: str | None = None
    to_status: str
    actor_id: str
    changed_at: datetime
    note: str | None = None


class ClaimDetail(ClaimOut):
    history: list[ClaimHistoryEntry] = Field(default_factory=list)
