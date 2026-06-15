from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.memory.manager import (
    DuplicateMemoryError,
    MemoryManager,
    MemoryNotFoundError,
    MemoryVersionConflictError,
)
from app.schemas.memory import MemoryCreate, MemoryUpdate


@pytest.fixture(autouse=True)
async def database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


def create_payload(content: str = "Learning PostgreSQL") -> MemoryCreate:
    return MemoryCreate(
        memory_type="learning_profile",
        scope="user",
        project_id=None,
        content=content,
        summary="PostgreSQL learning",
        importance=Decimal("0.8000"),
        confidence=Decimal("0.9000"),
        tags=["postgresql"],
        expires_at=None,
    )


@pytest.mark.anyio
async def test_manual_create_rejects_active_duplicate() -> None:
    user_id = uuid4()
    async with async_session_factory() as session:
        manager = MemoryManager(session)
        await manager.create_manual(user_id=user_id, payload=create_payload())
        with pytest.raises(DuplicateMemoryError):
            await manager.create_manual(
                user_id=user_id,
                payload=create_payload("  Learning   PostgreSQL "),
            )


@pytest.mark.anyio
async def test_consolidation_reuses_active_duplicate() -> None:
    user_id = uuid4()
    run_id = uuid4()
    async with async_session_factory() as session:
        manager = MemoryManager(session)
        first = await manager.create_consolidated(
            user_id=user_id,
            run_id=run_id,
            skill_version="1.1.0",
            payload=create_payload(),
        )
        second = await manager.create_consolidated(
            user_id=user_id,
            run_id=uuid4(),
            skill_version="1.1.0",
            payload=create_payload("Learning PostgreSQL"),
        )

    assert first.created is True
    assert second.created is False
    assert second.deduplicated is True
    assert first.memory.memory_id == second.memory.memory_id


@pytest.mark.anyio
async def test_update_increments_version_and_recomputes_hash() -> None:
    user_id = uuid4()
    async with async_session_factory() as session:
        manager = MemoryManager(session)
        created = await manager.create_manual(
            user_id=user_id,
            payload=create_payload(),
        )
        old_hash = created.content_hash
        updated = await manager.update(
            memory_id=created.memory_id,
            user_id=user_id,
            payload=MemoryUpdate(
                version=1,
                content="Learning PostgreSQL query planning",
            ),
        )

    assert updated.version == 2
    assert updated.content_hash != old_hash


@pytest.mark.anyio
async def test_update_rejects_stale_version() -> None:
    user_id = uuid4()
    async with async_session_factory() as session:
        manager = MemoryManager(session)
        created = await manager.create_manual(
            user_id=user_id,
            payload=create_payload(),
        )
        await manager.update(
            memory_id=created.memory_id,
            user_id=user_id,
            payload=MemoryUpdate(version=1, summary="Updated once"),
        )
        with pytest.raises(MemoryVersionConflictError):
            await manager.update(
                memory_id=created.memory_id,
                user_id=user_id,
                payload=MemoryUpdate(version=1, summary="Stale update"),
            )


@pytest.mark.anyio
async def test_soft_delete_hides_memory_and_allows_recreate() -> None:
    user_id = uuid4()
    async with async_session_factory() as session:
        manager = MemoryManager(session)
        created = await manager.create_manual(
            user_id=user_id,
            payload=create_payload(),
        )
        await manager.delete(
            memory_id=created.memory_id,
            user_id=user_id,
            version=1,
        )
        with pytest.raises(MemoryNotFoundError):
            await manager.get(memory_id=created.memory_id, user_id=user_id)
        recreated = await manager.create_manual(
            user_id=user_id,
            payload=create_payload(),
        )

    assert recreated.memory_id != created.memory_id
