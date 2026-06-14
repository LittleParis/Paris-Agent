from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner
from app.db.base import Base
from app.db.models.agent_run import AgentRun
from app.db.session import engine
from app.db.session import async_session_factory


@pytest.fixture(autouse=True)
async def database() -> None:
    agent_run_event_broker.clear()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await mock_agent_runner.wait_for_all()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
async def test_create_agent_run_returns_accepted_contract() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/agent/runs",
            json={
                "thread_id": None,
                "project_id": None,
                "skill_id": None,
                "task_type": "chat",
                "input": "Kafka 为什么能够保证高吞吐？",
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["detail_url"] == f"/api/agent/runs/{body['run_id']}"
    assert body["events_url"] == f"/api/agent/runs/{body['run_id']}/events"
    assert response.headers["location"] == body["detail_url"]


@pytest.mark.anyio
async def test_create_agent_run_rejects_blank_input() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/agent/runs",
            json={"input": "   "},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_get_agent_run_returns_completed_mock_result() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/agent/runs",
            json={"input": "解释 Kafka 的高吞吐设计"},
        )
        run_id = created.json()["run_id"]
        await mock_agent_runner.wait_for_all()

        response = await client.get(f"/api/agent/runs/{run_id}")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run_id,
        "thread_id": None,
        "user_id": "00000000-0000-0000-0000-000000000001",
        "project_id": None,
        "skill_id": None,
        "task_type": "chat",
        "status": "succeeded",
        "current_node": None,
        "input": "解释 Kafka 的高吞吐设计",
        "final_output": "这是 Paris Agent 的模拟回复。",
        "error_message": None,
        "total_tokens": 32,
        "total_cost": "0.00000000",
        "created_at": response.json()["created_at"],
        "updated_at": response.json()["updated_at"],
    }


@pytest.mark.anyio
async def test_get_agent_run_returns_not_found() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/agent/runs/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent run not found"}


@pytest.mark.anyio
async def test_agent_run_events_stream_mock_sequence() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/agent/runs",
            json={"input": "返回模拟执行事件"},
        )
        run_id = created.json()["run_id"]
        response = await client.get(f"/api/agent/runs/{run_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    event_types = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert event_types == [
        "run.started",
        "node.started",
        "message.delta",
        "message.delta",
        "node.completed",
        "run.completed",
    ]
    assert '"sequence":6' in response.text
    assert '"output":"这是 Paris Agent 的模拟回复。"' in response.text


@pytest.mark.anyio
async def test_agent_run_database_constraints_reject_invalid_values() -> None:
    async with async_session_factory() as session:
        session.add(
            AgentRun(
                user_id=uuid4(),
                input="valid input",
                status="unknown",
                total_tokens=-1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
