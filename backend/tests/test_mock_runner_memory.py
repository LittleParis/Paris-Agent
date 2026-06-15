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
