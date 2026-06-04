from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Standalone JWT — independent of the Shared Data API. The dashboard signs
    # its own admin tokens so it stays usable when SDA is down (ADR-006).
    jwt_secret: str = Field(alias="DASHBOARD_JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="DASHBOARD_JWT_ALGORITHM")
    jwt_expires_minutes: int = Field(default=60, alias="DASHBOARD_JWT_EXPIRES_MINUTES")

    # Single admin, supplied entirely by env. The plaintext password is read
    # once at startup, bcrypt-hashed, and the plaintext reference is dropped
    # from app state.
    admin_username: str = Field(alias="DASHBOARD_ADMIN_USERNAME")
    admin_password: str = Field(alias="DASHBOARD_ADMIN_PASSWORD")

    # Reserved for Phase 7d (Chroma + embeddings) — loaded but unused in 7a.
    chroma_url: str = Field(
        default="http://chroma:8000",
        alias="DASHBOARD_CHROMA_URL",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
