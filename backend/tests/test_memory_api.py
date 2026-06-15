from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner
from app.core.config import get_settings
from app.db.base import Base
from app.db.models.agent_memory import AgentMemory  # noqa: F401
from app.db.models.runtime_event import RuntimeEvent  # noqa: F401
from app.db.session import engine
from app.main import app
from app.skills.registry import skill_registry
from tests.conftest import sync_skills_for_test


@pytest.fixture(autouse=True)
async def database() -> None:
    agent_run_event_broker.clear()
    skill_registry._ready = False
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await sync_skills_for_test()
    yield
    await mock_agent_runner.wait_for_all()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
async def test_memory_crud_search_and_soft_delete() -> None:
    project_id = uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created_response = await client.post(
            "/api/v1/memories",
            json={
                "memory_type": "project",
                "scope": "project",
                "project_id": str(project_id),
                "content": "PostgreSQL is the canonical memory store.",
                "summary": "Canonical store",
                "importance": "0.8000",
                "confidence": "0.9000",
                "tags": ["p6", "postgresql"],
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()

        listed = await client.get(
            "/api/v1/memories",
            params={"project_id": str(project_id), "tag": "p6"},
        )
        assert listed.status_code == 200
        assert listed.json()["items"][0]["memory_id"] == created["memory_id"]

        searched = await client.post(
            "/api/v1/memories/search",
            json={
                "query": "PostgreSQL canonical",
                "project_id": str(project_id),
                "limit": 5,
            },
        )
        assert searched.status_code == 200
        assert searched.json()["items"][0]["memory"]["memory_id"] == created["memory_id"]

        updated = await client.patch(
            f"/api/v1/memories/{created['memory_id']}",
            json={"version": 1, "summary": "PostgreSQL canonical record"},
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == 2

        deleted = await client.delete(
            f"/api/v1/memories/{created['memory_id']}",
            params={"version": 2},
        )
        assert deleted.status_code == 204

        missing = await client.get(
            f"/api/v1/memories/{created['memory_id']}"
        )
        assert missing.status_code == 404


@pytest.mark.anyio
async def test_duplicate_create_returns_existing_memory_id() -> None:
    settings = get_settings()
    payload = {
        "memory_type": "semantic",
        "scope": "user",
        "content": "A stable duplicate fact.",
        "importance": "0.5000",
        "confidence": "0.8000",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post("/api/v1/memories", json=payload)
        second = await client.post(
            "/api/v1/memories",
            json={**payload, "content": " A  stable duplicate fact. "},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["memory_id"] == first.json()["memory_id"]
    assert settings.default_user_id
