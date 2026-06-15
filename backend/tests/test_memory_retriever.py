from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.base import Base
from app.db.repositories.memories import MemoryRepository
from app.db.session import async_session_factory, engine
from app.memory.manager import MemoryManager
from app.memory.retriever import MemoryRetriever
from app.schemas.memory import MemoryCreate


def build_settings() -> Settings:
    return Settings(
        app_name="Paris Agent",
        service_name="paris-agent-backend",
        environment="test",
        api_host="127.0.0.1",
        api_port=8000,
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        rabbitmq_url="amqp://guest:guest@localhost:5672//",
        memory_text_weight=0.40,
        memory_importance_weight=0.20,
        memory_confidence_weight=0.10,
        memory_recency_weight=0.10,
        memory_access_weight=0.05,
        memory_project_weight=0.15,
    )


@pytest.fixture(autouse=True)
async def database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
async def test_search_ranks_text_and_project_match_first() -> None:
    user_id = uuid4()
    project_id = uuid4()
    async with async_session_factory() as session:
        manager = MemoryManager(session)
        exact = await manager.create_manual(
            user_id=user_id,
            payload=MemoryCreate(
                memory_type="project",
                scope="project",
                project_id=project_id,
                content="Paris Agent uses Milvus for vector retrieval in P7.",
                summary="Milvus retrieval",
                importance=Decimal("0.8000"),
                confidence=Decimal("0.9000"),
                tags=["milvus", "p7"],
            ),
        )
        await manager.create_manual(
            user_id=user_id,
            payload=MemoryCreate(
                memory_type="semantic",
                scope="user",
                content="PostgreSQL stores canonical memory records.",
                importance=Decimal("1.0000"),
                confidence=Decimal("1.0000"),
                tags=["postgresql"],
            ),
        )

        retriever = MemoryRetriever(
            repository=MemoryRepository(session),
            settings=build_settings(),
        )
        hits = await retriever.search(
            user_id=user_id,
            query="Milvus vector retrieval",
            project_id=project_id,
            memory_types=[],
            tags=[],
            limit=10,
            touch_access=False,
        )

    assert hits[0].memory.memory_id == exact.memory_id
    assert hits[0].score > hits[1].score
    assert hits[0].score_breakdown.project_relevance == 1.0


@pytest.mark.anyio
async def test_runtime_search_updates_access_statistics() -> None:
    user_id = uuid4()
    async with async_session_factory() as session:
        manager = MemoryManager(session)
        memory = await manager.create_manual(
            user_id=user_id,
            payload=MemoryCreate(
                memory_type="semantic",
                scope="user",
                content="FastAPI dependencies use Depends.",
                importance=Decimal("0.5000"),
                confidence=Decimal("0.8000"),
            ),
        )
        retriever = MemoryRetriever(
            repository=MemoryRepository(session),
            settings=build_settings(),
        )

        await retriever.search(
            user_id=user_id,
            query="FastAPI Depends",
            project_id=None,
            memory_types=[],
            tags=[],
            limit=5,
            touch_access=True,
        )
        refreshed = await MemoryRepository(session).get_owned(
            memory.memory_id,
            user_id,
        )

    assert refreshed is not None
    assert refreshed.access_count == 1
    assert refreshed.last_accessed_at is not None


@pytest.mark.anyio
async def test_recency_score_decays_monotonically() -> None:
    now = datetime.now(UTC)

    recent = MemoryRetriever.recency_score(now - timedelta(hours=1), now)
    old = MemoryRetriever.recency_score(now - timedelta(days=60), now)

    assert 0 <= old < recent <= 1
