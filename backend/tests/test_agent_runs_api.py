from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner
from app.db.base import Base
from app.db.models.agent_run import AgentRun
from app.db.models.runtime_event import RuntimeEvent  # noqa: F401
from app.db.session import engine
from app.db.session import async_session_factory
from tests.conftest import sync_skills_for_test
from app.skills.registry import skill_registry


@pytest.fixture(autouse=True)
async def database() -> None:
    agent_run_event_broker.clear()
    # Reset registry state for each test
    skill_registry._ready = False
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    # Sync skills for P5 tests
    await sync_skills_for_test()
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
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "succeeded"
    assert body["skill_id"] == "tech_qa"
    assert body["skill_version"] == "1.1.0"
    assert body["skill_selection_mode"] == "default"
    assert body["final_output"] == "这是 Paris Agent 的模拟回复。"
    assert body["total_tokens"] == 32


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
        await mock_agent_runner.wait_for_all()
        response = await client.get(f"/api/agent/runs/{run_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    # 解析 SSE 事件类型
    event_types = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert event_types == [
        "skill.matched",
        "run.started",
        "memory.retrieval.started",
        "memory.retrieval.completed",
        "node.started",
        "message.delta",
        "message.delta",
        "node.completed",
        "run.completed",
    ]

    # 9 events now (7 base + 2 memory retrieval)
    sse_ids = [
        line.removeprefix("id: ")
        for line in response.text.splitlines()
        if line.startswith("id: ")
    ]
    assert len(sse_ids) == 9
    uuids = [__import__("uuid").UUID(sid) for sid in sse_ids]
    assert len(set(uuids)) == 9

    # 验证 JSON 数据中的 sequence 和 payload
    import json

    data_lines = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert len(data_lines) == 9
    sequences = [d["sequence"] for d in data_lines]
    assert sequences == [1, 2, 3, 4, 5, 6, 7, 8, 9]

    # 验证稳定事件信封字段
    for data in data_lines:
        assert "event_id" in data
        assert "run_id" in data
        assert "timestamp" in data
        assert "status" in data
        assert "payload" in data

    # skill.matched is the first event
    assert data_lines[0]["payload"]["skill_id"] == "tech_qa"
    assert data_lines[0]["payload"]["skill_version"] == "1.1.0"
    assert data_lines[0]["payload"]["skill_selection_mode"] == "default"

    # memory.retrieval.started has the query
    assert data_lines[2]["payload"]["memory_query"] == "返回模拟执行事件"
    # memory.retrieval.completed has memories list
    assert "memories" in data_lines[3]["payload"]

    # The rest of the payload checks (shifted by +2 for memory events)
    assert data_lines[4]["payload"]["node_name"] == "mock_executor"
    assert data_lines[5]["payload"]["delta"] == "这是 Paris Agent "
    assert data_lines[6]["payload"]["delta"] == "的模拟回复。"
    assert data_lines[8]["payload"]["output"] == "这是 Paris Agent 的模拟回复。"


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


# ===== P4 SSE 新测试 =====


@pytest.mark.anyio
async def test_sse_unknown_run_returns_404() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/agent/runs/{uuid4()}/events")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_sse_invalid_last_event_id_returns_400() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/agent/runs",
            json={"input": "测试非法 Last-Event-ID"},
        )
        run_id = created.json()["run_id"]
        response = await client.get(
            f"/api/agent/runs/{run_id}/events",
            headers={"Last-Event-ID": "not-a-valid-uuid"},
        )

    assert response.status_code == 400
    assert "Last-Event-ID" in response.json()["detail"]


@pytest.mark.anyio
async def test_sse_unknown_last_event_id_returns_400() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/agent/runs",
            json={"input": "测试未知事件 ID"},
        )
        run_id = created.json()["run_id"]
        await mock_agent_runner.wait_for_all()
        response = await client.get(
            f"/api/agent/runs/{run_id}/events",
            headers={"Last-Event-ID": str(uuid4())},
        )

    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


@pytest.mark.anyio
async def test_sse_cross_run_last_event_id_returns_400() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 创建两个 Run
        run1 = await client.post(
            "/api/agent/runs",
            json={"input": "第一个 Run"},
        )
        run1_id = run1.json()["run_id"]
        await mock_agent_runner.wait_for_all()

        run2 = await client.post(
            "/api/agent/runs",
            json={"input": "第二个 Run"},
        )
        run2_id = run2.json()["run_id"]
        await mock_agent_runner.wait_for_all()

        # 获取 Run 1 的第一个事件的 event_id
        resp1 = await client.get(f"/api/agent/runs/{run1_id}/events")
        import json

        data_lines = [
            json.loads(line.removeprefix("data: "))
            for line in resp1.text.splitlines()
            if line.startswith("data: ")
        ]
        run1_event_id = data_lines[0]["event_id"]

        # 用 Run 1 的事件 ID 去请求 Run 2 的 SSE
        response = await client.get(
            f"/api/agent/runs/{run2_id}/events",
            headers={"Last-Event-ID": run1_event_id},
        )

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]


@pytest.mark.anyio
async def test_sse_last_event_id_replays_only_subsequent() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/agent/runs",
            json={"input": "测试 Last-Event-ID 回放"},
        )
        run_id = created.json()["run_id"]
        await mock_agent_runner.wait_for_all()

        # 先获取完整事件列表
        full_resp = await client.get(f"/api/agent/runs/{run_id}/events")
        import json

        full_data = [
            json.loads(line.removeprefix("data: "))
            for line in full_resp.text.splitlines()
            if line.startswith("data: ")
        ]
        # 用第 3 个事件（memory.retrieval.started, sequence=3）作为游标
        cursor_event_id = full_data[2]["event_id"]

        # 使用 Last-Event-ID 重连
        replay_resp = await client.get(
            f"/api/agent/runs/{run_id}/events",
            headers={"Last-Event-ID": cursor_event_id},
        )

    replay_types = [
        line.removeprefix("event: ")
        for line in replay_resp.text.splitlines()
        if line.startswith("event: ")
    ]
    # 应该只收到 sequence > 3 的事件
    assert replay_types == [
        "memory.retrieval.completed",
        "node.started",
        "message.delta",
        "message.delta",
        "node.completed",
        "run.completed",
    ]

    replay_data = [
        json.loads(line.removeprefix("data: "))
        for line in replay_resp.text.splitlines()
        if line.startswith("data: ")
    ]
    replay_sequences = [d["sequence"] for d in replay_data]
    assert replay_sequences == [4, 5, 6, 7, 8, 9]
