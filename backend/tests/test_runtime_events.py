"""Runtime Event Model 和 Repository 测试。

覆盖事件创建、序号分配、持久化、查询和数据库约束。
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner
from app.db.base import Base
from app.db.models.agent_run import AgentRun
from app.db.models.runtime_event import RuntimeEvent  # noqa: F401
from app.db.repositories.agent_runs import AgentRunRepository
from app.db.repositories.runtime_events import RuntimeEventRepository
from app.db.session import engine, async_session_factory
from app.schemas.agent import RuntimeEventPayload


@pytest.fixture(autouse=True)
async def database() -> None:
    agent_run_event_broker.clear()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await mock_agent_runner.wait_for_all()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def _create_run(input_text: str = "test input") -> AgentRun:
    """辅助函数：创建一个 queued 状态的 Run。"""

    async with async_session_factory() as session:
        repo = AgentRunRepository(session)
        return await repo.create(
            user_id=uuid4(),
            input_text=input_text,
            thread_id=None,
            project_id=None,
            skill_id=None,
            task_type="chat",
        )


@pytest.mark.anyio
async def test_append_event_persists_to_database() -> None:
    run = await _create_run()

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        event = await repo.append(
            run_id=run.run_id,
            event_type="run.started",
            status="running",
            payload=RuntimeEventPayload(node_name="test_node"),
        )

    assert event.id > 0
    assert event.run_id == run.run_id
    assert event.sequence == 1
    assert event.event_type == "run.started"
    assert event.status == "running"
    assert event.payload["node_name"] == "test_node"


@pytest.mark.anyio
async def test_sequence_starts_from_one_and_increments() -> None:
    run = await _create_run()

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        e1 = await repo.append(
            run_id=run.run_id,
            event_type="run.started",
            status="running",
        )
        e2 = await repo.append(
            run_id=run.run_id,
            event_type="node.started",
            status="running",
            payload=RuntimeEventPayload(node_name="n1"),
        )
        e3 = await repo.append(
            run_id=run.run_id,
            event_type="message.delta",
            status="running",
            payload=RuntimeEventPayload(delta="hello"),
        )

    assert e1.sequence == 1
    assert e2.sequence == 2
    assert e3.sequence == 3


@pytest.mark.anyio
async def test_different_runs_each_start_from_one() -> None:
    run_a = await _create_run("input A")
    run_b = await _create_run("input B")

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        a1 = await repo.append(
            run_id=run_a.run_id,
            event_type="run.started",
            status="running",
        )
        b1 = await repo.append(
            run_id=run_b.run_id,
            event_type="run.started",
            status="running",
        )
        a2 = await repo.append(
            run_id=run_a.run_id,
            event_type="node.started",
            status="running",
            payload=RuntimeEventPayload(node_name="n1"),
        )
        b2 = await repo.append(
            run_id=run_b.run_id,
            event_type="node.started",
            status="running",
            payload=RuntimeEventPayload(node_name="n2"),
        )

    assert a1.sequence == 1
    assert a2.sequence == 2
    assert b1.sequence == 1
    assert b2.sequence == 2


@pytest.mark.anyio
async def test_list_after_sequence_returns_events_in_order() -> None:
    run = await _create_run()

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        await repo.append(run_id=run.run_id, event_type="run.started", status="running")
        await repo.append(
            run_id=run.run_id, event_type="node.started", status="running",
            payload=RuntimeEventPayload(node_name="n1"),
        )
        await repo.append(
            run_id=run.run_id, event_type="message.delta", status="running",
            payload=RuntimeEventPayload(delta="hello"),
        )

        events = await repo.list_after_sequence(run.run_id, 1)

    assert len(events) == 2
    assert events[0].sequence == 2
    assert events[1].sequence == 3
    assert events[0].event_type == "node.started"
    assert events[1].event_type == "message.delta"


@pytest.mark.anyio
async def test_get_by_event_id_returns_correct_event() -> None:
    run = await _create_run()

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        created = await repo.append(
            run_id=run.run_id,
            event_type="run.started",
            status="running",
        )
        found = await repo.get_by_event_id(created.event_id)

    assert found is not None
    assert found.event_id == created.event_id
    assert found.run_id == run.run_id


@pytest.mark.anyio
async def test_get_by_event_id_returns_none_for_unknown() -> None:
    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        found = await repo.get_by_event_id(uuid4())

    assert found is None


@pytest.mark.anyio
async def test_get_last_sequence_returns_max() -> None:
    run = await _create_run()

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        # 空时返回 0
        assert await repo.get_last_sequence(run.run_id) == 0

        await repo.append(run_id=run.run_id, event_type="run.started", status="running")
        await repo.append(
            run_id=run.run_id, event_type="node.started", status="running",
            payload=RuntimeEventPayload(node_name="n1"),
        )
        assert await repo.get_last_sequence(run.run_id) == 2


@pytest.mark.anyio
async def test_to_envelope_converts_correctly() -> None:
    run = await _create_run()

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        event = await repo.append(
            run_id=run.run_id,
            event_type="message.delta",
            status="running",
            payload=RuntimeEventPayload(node_name="executor", delta="hi"),
        )
        envelope = RuntimeEventRepository.to_envelope(event)

    assert envelope.event_id == event.event_id
    assert envelope.event_type == "message.delta"
    assert envelope.run_id == run.run_id
    assert envelope.sequence == 1
    assert envelope.status == "running"
    assert envelope.payload.node_name == "executor"
    assert envelope.payload.delta == "hi"


@pytest.mark.anyio
async def test_database_rejects_zero_sequence() -> None:
    """sequence <= 0 应被 CHECK 约束拒绝。"""

    run = await _create_run()

    async with async_session_factory() as session:
        session.add(
            RuntimeEvent(
                event_id=uuid4(),
                run_id=run.run_id,
                sequence=0,
                event_type="run.started",
                status="running",
                payload={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_database_rejects_invalid_status() -> None:
    """status 不在合法集合内应被 CHECK 约束拒绝。"""

    run = await _create_run()

    async with async_session_factory() as session:
        session.add(
            RuntimeEvent(
                event_id=uuid4(),
                run_id=run.run_id,
                sequence=1,
                event_type="run.started",
                status="invalid_status",
                payload={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_database_rejects_duplicate_sequence() -> None:
    """同一 Run 内的重复 sequence 应被唯一约束拒绝。"""

    run = await _create_run()

    async with async_session_factory() as session:
        session.add(
            RuntimeEvent(
                event_id=uuid4(),
                run_id=run.run_id,
                sequence=1,
                event_type="run.started",
                status="running",
                payload={},
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        session.add(
            RuntimeEvent(
                event_id=uuid4(),
                run_id=run.run_id,
                sequence=1,  # 重复
                event_type="node.started",
                status="running",
                payload={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_database_rejects_blank_event_type() -> None:
    """空白 event_type 应被 CHECK 约束拒绝。"""

    run = await _create_run()

    async with async_session_factory() as session:
        session.add(
            RuntimeEvent(
                event_id=uuid4(),
                run_id=run.run_id,
                sequence=1,
                event_type="   ",
                status="running",
                payload={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_events_cascade_deleted_with_run() -> None:
    """删除 Run 时应级联删除关联的 runtime_events。"""

    run = await _create_run()
    run_id = run.run_id

    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        await repo.append(run_id=run_id, event_type="run.started", status="running")
        await repo.append(
            run_id=run_id, event_type="node.started", status="running",
            payload=RuntimeEventPayload(node_name="n1"),
        )
        assert await repo.get_last_sequence(run_id) == 2

    # 删除 Run
    async with async_session_factory() as session:
        run_repo = AgentRunRepository(session)
        run_obj = await run_repo.get_by_run_id(run_id)
        assert run_obj is not None
        await session.delete(run_obj)
        await session.commit()

    # 事件应已被级联删除
    async with async_session_factory() as session:
        repo = RuntimeEventRepository(session)
        assert await repo.get_last_sequence(run_id) == 0
