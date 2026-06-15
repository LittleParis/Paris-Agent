"""P6 Task 9: Mock Runner Memory 读写集成测试。"""

from uuid import uuid4

import pytest

from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import MockAgentRunner
from app.db.base import Base
from app.db.models.agent_memory import AgentMemory  # noqa: F401
from app.db.models.runtime_event import RuntimeEvent  # noqa: F401
from app.db.repositories.memories import MemoryRepository
from app.db.session import async_session_factory, engine
from app.memory.manager import MemoryManager
from app.schemas.agent import RuntimeEventPayload


@pytest.fixture(autouse=True)
async def database() -> None:
    agent_run_event_broker.clear()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
async def test_runtime_payload_accepts_memory_summaries() -> None:
    payload = RuntimeEventPayload(
        memory_query="FastAPI",
        memories=[
            {
                "memory_id": str(uuid4()),
                "memory_type": "semantic",
                "summary": "FastAPI uses Depends.",
                "score": 0.9,
            }
        ],
        memory_write_count=1,
    )

    assert payload.memory_query == "FastAPI"
    assert payload.memory_write_count == 1


@pytest.mark.anyio
async def test_memory_consolidation_writes_only_through_manager() -> None:
    runner = MockAgentRunner(event_broker=None)
    user_id = uuid4()
    run_id = uuid4()

    async with async_session_factory() as session:
        results = await runner._consolidate_memories(
            session=session,
            user_id=user_id,
            project_id=None,
            run_id=run_id,
            skill_version="1.1.0",
            text="Remember that FastAPI uses dependency injection.",
        )
        rows = await MemoryRepository(session).search_candidates(
            user_id=user_id,
            project_id=None,
            memory_types=[],
            tags=[],
        )

    assert len(results) == 1
    assert len(rows) == 1
    assert rows[0].source_type == "consolidation"


@pytest.mark.anyio
async def test_retrieve_memories_returns_empty_for_no_stored_memories() -> None:
    runner = MockAgentRunner(event_broker=None)
    user_id = uuid4()

    async with async_session_factory() as session:
        hits = await runner._retrieve_memories(
            session=session,
            user_id=user_id,
            project_id=None,
            query="PostgreSQL indexing strategies",
        )

    assert hits == []


@pytest.mark.anyio
async def test_consolidation_batch_is_atomic() -> None:
    """C3 fix: if consolidation fails partway through,
    no partial results should be committed to the database."""

    from decimal import Decimal

    from app.schemas.memory import ConsolidationMemoryCommand

    runner = MockAgentRunner(event_broker=None)
    user_id = uuid4()
    run_id = uuid4()

    # Produce 2 mock commands so the batch loop iterates more than once.
    fake_commands = [
        ConsolidationMemoryCommand(
            memory_type="semantic",
            scope="user",
            project_id=None,
            content=f"fact number {i}",
            summary=f"summary {i}",
            importance=Decimal("0.5000"),
            confidence=Decimal("0.5000"),
            tags=["test"],
            source_detail={"test": True},
        )
        for i in range(2)
    ]

    # Monkey-patch extractor to return 2 commands.
    runner.memory_extractor.extract = lambda **kwargs: fake_commands

    # Monkey-patch create_consolidated to succeed once then fail.
    original_create = MemoryManager.create_consolidated
    call_count = 0

    async def patched_create(self, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return await original_create(self, **kwargs)
        raise RuntimeError("simulated mid-batch failure")

    MemoryManager.create_consolidated = patched_create
    try:
        async with async_session_factory() as session:
            with pytest.raises(RuntimeError, match="simulated mid-batch failure"):
                await runner._consolidate_memories(
                    session=session,
                    user_id=user_id,
                    project_id=None,
                    run_id=run_id,
                    skill_version="1.1.0",
                    text="trigger two commands",
                )
    finally:
        MemoryManager.create_consolidated = original_create

    # Verify nothing was committed from the partial batch.
    async with async_session_factory() as session:
        rows = await MemoryRepository(session).search_candidates(
            user_id=user_id,
            project_id=None,
            memory_types=[],
            tags=[],
        )
    assert len(rows) == 0, "No memories should persist after atomic rollback"
