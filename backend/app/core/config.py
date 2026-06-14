from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    service_name: str
    environment: str
    api_host: str
    api_port: int
    database_url: str
    redis_url: str
    rabbitmq_url: str
    default_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    mock_run_step_delay_seconds: float = 0.01

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
