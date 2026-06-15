"""P5 Skills API 契约测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner
from app.db.base import Base
from app.db.models import (  # noqa: F401
    AgentRun, AgentSkill, AgentSkillRun, AgentSkillVersion, RuntimeEvent,
)
from app.db.session import engine, async_session_factory
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
async def test_list_skills_returns_enabled_by_default():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/skills")

    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 8
    # All enabled
    assert all(item["enabled"] for item in items)
    # Default skill first
    assert items[0]["is_default"] is True
    assert items[0]["skill_id"] == "tech_qa"


@pytest.mark.anyio
async def test_list_skills_includes_version():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/skills")

    items = response.json()
    for item in items:
        assert "version" in item
        assert item["version"] in ("1.0.0", "1.1.0")


@pytest.mark.anyio
async def test_get_skill_detail_returns_public_fields():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/skills/tech_qa")

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "tech_qa"
    assert body["name"] == "Technical Q&A"
    assert body["version"] == "1.1.0"
    assert body["is_default"] is True
    assert body["enabled"] is True
    assert "input_schema" in body
    assert "output_schema" in body
    assert "workflow" in body
    assert "memory_policy" in body
    assert "safety_policy" in body
    assert "runtime_config" in body
    assert "tools" in body


@pytest.mark.anyio
async def test_get_skill_detail_excludes_internal_fields():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/skills/tech_qa")

    body = response.json()
    # Should NOT contain these internal fields
    assert "prompt" not in body
    assert "content_hash" not in body
    assert "source_path" not in body


@pytest.mark.anyio
async def test_get_unknown_skill_returns_404():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/skills/nonexistent_skill")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_create_run_with_default_skill():
    """Creating a run without skill_id uses tech_qa as default."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/agent/runs",
            json={"input": "Test default skill selection"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["skill_id"] == "tech_qa"
    assert body["skill_version"] == "1.1.0"
    assert body["skill_selection_mode"] == "default"


@pytest.mark.anyio
async def test_create_run_with_explicit_skill():
    """Creating a run with explicit skill_id."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/agent/runs",
            json={"input": "Test explicit skill", "skill_id": "learning_path"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["skill_id"] == "learning_path"
    assert body["skill_version"] == "1.1.0"
    assert body["skill_selection_mode"] == "explicit"


@pytest.mark.anyio
async def test_create_run_with_unknown_skill_returns_422():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/agent/runs",
            json={"input": "Test unknown skill", "skill_id": "nonexistent"},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_skill_matched_is_first_event():
    """skill.matched should be the first event in the sequence."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/agent/runs",
            json={"input": "Test event order"},
        )
        run_id = created.json()["run_id"]
        await mock_agent_runner.wait_for_all()
        response = await client.get(f"/api/agent/runs/{run_id}/events")

    import json
    data_lines = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    event_types = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]

    assert event_types[0] == "skill.matched"
    assert data_lines[0]["sequence"] == 1
    assert data_lines[0]["payload"]["skill_id"] == "tech_qa"
    assert data_lines[0]["payload"]["skill_version"] == "1.1.0"
    assert data_lines[0]["payload"]["skill_selection_mode"] == "default"
