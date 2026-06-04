from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AdminOut(BaseModel):
    username: str
    role: str


class HealthResponse(BaseModel):
    status: str
