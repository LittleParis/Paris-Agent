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
        "SSE_HEARTBEAT_SECONDS": "0.1",
    }
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def sync_skills_for_test() -> None:
    """Load and sync skill definitions for test setup."""
    from app.skills.loader import load_all_skill_definitions
    from app.skills.validator import validate_skill_definition_set
    from app.skills.synchronizer import sync_skill_definitions
    from app.skills.registry import skill_registry
    from app.db.session import async_session_factory

    definitions = load_all_skill_definitions()
    validate_skill_definition_set(definitions)
    async with async_session_factory() as session:
        await sync_skill_definitions(session, definitions)
    skill_registry.mark_ready()
