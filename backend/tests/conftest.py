import os

import pytest


os.environ.update(
    {
        "APP_NAME": "Paris Agent API",
        "SERVICE_NAME": "paris-agent-api",
        "ENVIRONMENT": "test",
        "API_HOST": "127.0.0.1",
        "API_PORT": "8000",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://:test@localhost:6379/0",
        "RABBITMQ_URL": "amqp://test:test@localhost:5672/",
        "DEFAULT_USER_ID": "00000000-0000-0000-0000-000000000001",
        "MOCK_RUN_STEP_DELAY_SECONDS": "0",
    }
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
