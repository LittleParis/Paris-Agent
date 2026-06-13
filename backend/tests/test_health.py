import os

import pytest
from httpx import ASGITransport, AsyncClient


os.environ.update(
    {
        "APP_NAME": "AGI Assistant API",
        "SERVICE_NAME": "agi-assistant-api",
        "ENVIRONMENT": "development",
        "API_HOST": "127.0.0.1",
        "API_PORT": "8000",
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
        "REDIS_URL": "redis://:test@localhost:6379/0",
        "RABBITMQ_URL": "amqp://test:test@localhost:5672/",
    }
)

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health_returns_service_status() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "agi-assistant-api",
            "environment": "development",
        }
