from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.base import Base
from app.db.models.agent_memory import AgentMemory
from app.db.repositories.memories import MemoryRepository
from app.db.session import async_session_factory, engine


@pytest.fixture(autouse=True)
async def database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def create_memory(
    *,
    user_id,
    content: str,
    memory_type: str = "semantic",
    scope: str = "user",
    project_id=None,
    tags: list[str] | None = None,
    expires_at=None,
) -> AgentMemory:
    async with async_session_factory() as session:
        repository = MemoryRepository(session)
        memory = await repository.create(
            user_id=user_id,
            project_id=project_id,
            memory_type=memory_type,
            scope=scope,
            content=content,
            summary=content,
            importance=Decimal("0.8000"),
            confidence=Decimal("0.9000"),
            source_type="manual",
            source_id=None,
            source_detail={"created_via": "test"},
            tags=tags or [],
            content_hash=(content.encode("utf-8").hex() + "0" * 64)[:64],
            expires_at=expires_at,
        )
        await session.commit()
        await session.refresh(memory)
        return memory


@pytest.mark.anyio
async def test_get_owned_hides_other_users() -> None:
    owner_id = uuid4()
    other_id = uuid4()
    memory = await create_memory(user_id=owner_id, content="owned")

    async with async_session_factory() as session:
        repository = MemoryRepository(session)
        assert await repository.get_owned(memory.memory_id, owner_id) is not None
        assert await repository.get_owned(memory.memory_id, other_id) is None


@pytest.mark.anyio
async def test_list_owned_excludes_expired_and_deleted_by_default() -> None:
    user_id = uuid4()
    active = await create_memory(user_id=user_id, content="active")
    await create_memory(
        user_id=user_id,
        content="expired",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    async with async_session_factory() as session:
        repository = MemoryRepository(session)
        deleted = await repository.get_owned(active.memory_id, user_id)
        assert deleted is not None
        deleted.deleted_at = datetime.now(UTC)
        await session.commit()

        items, cursor = await repository.list_owned(
            user_id=user_id,
            memory_type=None,
            scope=None,
            project_id=None,
            tag=None,
            include_expired=False,
            limit=20,
            cursor=None,
        )

    assert items == []
    assert cursor is None


@pytest.mark.anyio
async def test_list_owned_uses_stable_cursor() -> None:
    user_id = uuid4()
    await create_memory(user_id=user_id, content="first")
    await create_memory(user_id=user_id, content="second")
    await create_memory(user_id=user_id, content="third")

    async with async_session_factory() as session:
        repository = MemoryRepository(session)
        first_page, cursor = await repository.list_owned(
            user_id=user_id,
            memory_type=None,
            scope=None,
            project_id=None,
            tag=None,
            include_expired=True,
            limit=2,
            cursor=None,
        )
        second_page, next_cursor = await repository.list_owned(
            user_id=user_id,
            memory_type=None,
            scope=None,
            project_id=None,
            tag=None,
            include_expired=True,
            limit=2,
            cursor=cursor,
        )

    assert len(first_page) == 2
    assert len(second_page) == 1
    assert cursor is not None
    assert next_cursor is None
    assert {item.memory_id for item in first_page}.isdisjoint(
        {item.memory_id for item in second_page}
    )


@pytest.mark.anyio
async def test_touch_access_batch_updates_only_owned_memories() -> None:
    owner_id = uuid4()
    other_id = uuid4()
    owned = await create_memory(user_id=owner_id, content="owned")
    foreign = await create_memory(user_id=other_id, content="foreign")

    async with async_session_factory() as session:
        repository = MemoryRepository(session)
        await repository.touch_access_batch(
            user_id=owner_id,
            memory_ids=[owned.memory_id, foreign.memory_id],
        )
        await session.commit()

    async with async_session_factory() as session:
        repository = MemoryRepository(session)
        owned_read = await repository.get_owned(owned.memory_id, owner_id)
        foreign_read = await repository.get_owned(foreign.memory_id, other_id)

    assert owned_read is not None
    assert foreign_read is not None
    assert owned_read.access_count == 1
    assert foreign_read.access_count == 0
