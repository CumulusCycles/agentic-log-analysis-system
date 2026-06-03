from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # JWT — shared with SDA; FNOL only decodes (never issues).
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    # Inter-service auth to SDA.
    shared_data_api_key_fnol: str = Field(alias="SHARED_DATA_API_KEY_FNOL")
    shared_data_api_base_url: str = Field(
        default="http://shared-data-api:8000",
        alias="SHARED_DATA_API_BASE_URL",
    )

    log_file_path: str = "/app/logs/fnol-app.log"


def get_settings() -> Settings:
    return Settings()
