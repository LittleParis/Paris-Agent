from functools import lru_cache
from uuid import UUID

from pydantic import Field, model_validator
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
    sse_heartbeat_seconds: float = 15.0
    memory_text_weight: float = Field(default=0.40, ge=0)
    memory_importance_weight: float = Field(default=0.20, ge=0)
    memory_confidence_weight: float = Field(default=0.10, ge=0)
    memory_recency_weight: float = Field(default=0.10, ge=0)
    memory_access_weight: float = Field(default=0.05, ge=0)
    memory_project_weight: float = Field(default=0.15, ge=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_memory_weights(self) -> "Settings":
        if self.memory_weight_total <= 0:
            raise ValueError("at least one memory weight must be positive")
        return self

    @property
    def memory_weight_total(self) -> float:
        return (
            self.memory_text_weight
            + self.memory_importance_weight
            + self.memory_confidence_weight
            + self.memory_recency_weight
            + self.memory_access_weight
            + self.memory_project_weight
        )

    def normalized_memory_weights(self) -> dict[str, float]:
        total = self.memory_weight_total
        return {
            "text_match": self.memory_text_weight / total,
            "importance": self.memory_importance_weight / total,
            "confidence": self.memory_confidence_weight / total,
            "recency": self.memory_recency_weight / total,
            "access_weight": self.memory_access_weight / total,
            "project_relevance": self.memory_project_weight / total,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
