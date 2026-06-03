from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    postgres_url: str = Field(alias="SHARED_DATA_API_POSTGRES_URL")
    mongodb_uri: str = Field(alias="SHARED_DATA_API_MONGODB_URI")
    mongodb_database: str = Field(default="insurance", alias="MONGO_INITDB_DATABASE")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expires_minutes: int = Field(default=60, alias="JWT_EXPIRES_MINUTES")

    api_key_fnol: str = Field(alias="SHARED_DATA_API_KEY_FNOL")
    api_key_customer_portal: str = Field(alias="SHARED_DATA_API_KEY_CUSTOMER_PORTAL")
    api_key_agent_portal: str = Field(alias="SHARED_DATA_API_KEY_AGENT_PORTAL")

    demo_customer_usernames: str = Field(default="", alias="DEMO_CUSTOMER_USERNAMES")
    demo_agent_usernames: str = Field(default="", alias="DEMO_AGENT_USERNAMES")

    simulator_tick_seconds: int = 30
    log_file_path: str = "/app/logs/shared-data-api.log"


def get_settings() -> Settings:
    return Settings()
