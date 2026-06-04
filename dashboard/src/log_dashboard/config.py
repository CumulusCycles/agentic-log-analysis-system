from functools import lru_cache
from pathlib import Path

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

    # Reserved for Phase 7d (Chroma + embeddings) — loaded but unused in 7a/7b.
    chroma_url: str = Field(
        default="http://chroma:8000",
        alias="DASHBOARD_CHROMA_URL",
    )

    # --- Phase 7b: log ingestion ---

    # Mount root for the 4 read-only log volumes. Tests override to point at
    # tests/fixtures/logs/. Production is the docker-compose mount path.
    log_volume_root: Path = Field(
        default=Path("/mnt/logs"),
        alias="DASHBOARD_LOG_VOLUME_ROOT",
    )

    # How many lines to tail from each app per /api/logs (or /api/status) call.
    # 10k × 4 apps × ~200 bytes ≈ 8 MB scanned per request — fast and bounded.
    logs_tail_default: int = Field(default=10_000, alias="DASHBOARD_LOGS_TAIL_DEFAULT")
    logs_tail_max: int = Field(default=50_000, alias="DASHBOARD_LOGS_TAIL_MAX")

    # Max entries returned in one /api/logs response (after filtering + sort).
    # Caps the wire payload; UI uses next_before for further pages.
    logs_page_default: int = Field(default=100, alias="DASHBOARD_LOGS_PAGE_DEFAULT")
    logs_page_max: int = Field(default=1_000, alias="DASHBOARD_LOGS_PAGE_MAX")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
