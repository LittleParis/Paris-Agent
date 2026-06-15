from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.db.models.agent_memory import AgentMemory
from app.db.session import async_session_factory, engine


@pytest.fixture(autouse=True)
async def database() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(AgentMemory.__table__.create)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(AgentMemory.__table__.drop)


def build_memory(**overrides) -> AgentMemory:
    values = {
        "memory_id": uuid4(),
        "user_id": uuid4(),
        "project_id": None,
        "memory_type": "learning_profile",
        "scope": "user",
        "content": "User is learning PostgreSQL indexing.",
        "summary": "Learning PostgreSQL indexing",
        "importance": Decimal("0.8000"),
        "confidence": Decimal("0.9000"),
        "source_type": "manual",
        "source_id": None,
        "content_hash": "a" * 64,
    }
    values.update(overrides)
    return AgentMemory(**values)


@pytest.mark.anyio
async def test_agent_memory_dialect_contracts_match_migration() -> None:
    postgresql_ddl = str(
        CreateTable(AgentMemory.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    sqlite_ddl = str(
        CreateTable(AgentMemory.__table__).compile(dialect=sqlite.dialect())
    )
    migration_source = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260614_0004_create_agent_memories.py"
    ).read_text(encoding="utf-8")

    postgresql_contract = (
        "CONSTRAINT ck_agent_memories_content_not_blank "
        "CHECK (length(btrim(content)) > 0)",
        "CONSTRAINT ck_agent_memories_summary_not_blank "
        "CHECK (summary IS NULL OR length(btrim(summary)) > 0)",
        "CONSTRAINT ck_agent_memories_source_detail_object "
        "CHECK (jsonb_typeof(source_detail) = 'object')",
        "CONSTRAINT ck_agent_memories_tags_array "
        "CHECK (jsonb_typeof(tags) = 'array')",
        "CONSTRAINT ck_agent_memories_content_hash "
        "CHECK (content_hash ~ '^[0-9a-f]{64}$')",
        "CONSTRAINT uq_agent_memories_memory_id UNIQUE (memory_id)",
        "source_detail JSONB DEFAULT '{}' NOT NULL",
        "tags JSONB DEFAULT '[]' NOT NULL",
    )
    for expected in postgresql_contract:
        assert expected in postgresql_ddl

    assert "length(trim(content)) > 0" in sqlite_ddl
    assert "summary IS NULL OR length(trim(summary)) > 0" in sqlite_ddl
    assert "length(content_hash) = 64" in sqlite_ddl
    assert "jsonb_typeof" not in sqlite_ddl
    assert "content_hash ~" not in sqlite_ddl

    migration_contract = (
        'name="ck_agent_memories_source_detail_object"',
        'name="ck_agent_memories_tags_array"',
        'name="ck_agent_memories_content_hash"',
        'name="uq_agent_memories_memory_id"',
        '"uq_agent_memories_active_content"',
        "'00000000-0000-0000-0000-000000000000'::uuid",
        'postgresql_where=sa.text("deleted_at IS NULL")',
        "server_default=sa.text(\"'{}'\")",
        "server_default=sa.text(\"'[]'\")",
    )
    for expected in migration_contract:
        assert expected in migration_source


@pytest.mark.anyio
async def test_agent_memory_constraint_metadata_is_explicitly_named() -> None:
    constraints = AgentMemory.__table__.constraints
    constraint_names = {
        constraint.name
        for constraint in constraints
        if isinstance(constraint, (CheckConstraint, UniqueConstraint))
    }

    assert "ck_agent_memories_content_hash" in constraint_names
    assert "ck_agent_memories_source_detail_object" in constraint_names
    assert "ck_agent_memories_tags_array" in constraint_names
    assert "uq_agent_memories_memory_id" in constraint_names


@pytest.mark.anyio
async def test_agent_memory_persists_valid_user_memory() -> None:
    async with async_session_factory() as session:
        memory = build_memory()
        session.add(memory)
        await session.commit()
        await session.refresh(memory)

    assert memory.id > 0
    assert memory.scope == "user"
    assert memory.project_id is None
    assert memory.source_detail == {}
    assert memory.tags == []
    assert memory.version == 1
    assert memory.access_count == 0
    assert memory.sync_status == "not_indexed"
    assert memory.external_vector_id is None
    assert memory.embedding_version is None
    assert memory.last_synced_at is None
    assert memory.sync_error is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "memory_type",
    [
        "short_term",
        "learning_profile",
        "semantic",
        "episodic",
        "project",
        "procedural",
        "task",
        "runtime",
    ],
)
async def test_agent_memory_accepts_all_memory_types(
    memory_type: str,
) -> None:
    overrides: dict[str, object] = {"memory_type": memory_type}
    if memory_type == "project":
        overrides.update(scope="project", project_id=uuid4())

    async with async_session_factory() as session:
        memory = build_memory(**overrides)
        session.add(memory)
        await session.commit()

    assert memory.memory_type == memory_type


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memory_type", "unknown"),
        ("scope", "workspace"),
        ("importance", Decimal("1.1000")),
        ("importance", Decimal("-0.1000")),
        ("confidence", Decimal("-0.1000")),
        ("confidence", Decimal("1.1000")),
        ("version", 0),
        ("access_count", -1),
        ("source_type", "chat"),
        ("sync_status", "indexed"),
        ("content", "   "),
        ("summary", "   "),
        ("content_hash", "a" * 63),
    ],
)
async def test_agent_memory_rejects_invalid_scalar_constraints(
    field: str,
    value: object,
) -> None:
    async with async_session_factory() as session:
        session.add(build_memory(**{field: value}))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_agent_memory_rejects_project_scope_without_project_id() -> None:
    async with async_session_factory() as session:
        session.add(build_memory(scope="project", project_id=None))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_agent_memory_rejects_user_scope_with_project_id() -> None:
    async with async_session_factory() as session:
        session.add(build_memory(scope="user", project_id=uuid4()))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_agent_memory_rejects_project_type_in_user_scope() -> None:
    async with async_session_factory() as session:
        session.add(build_memory(memory_type="project", scope="user"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_agent_memory_accepts_project_type_in_project_scope() -> None:
    project_id = uuid4()
    async with async_session_factory() as session:
        memory = build_memory(
            memory_type="project",
            scope="project",
            project_id=project_id,
        )
        session.add(memory)
        await session.commit()

    assert memory.scope == "project"
    assert memory.project_id == project_id


@pytest.mark.anyio
async def test_agent_memory_rejects_manual_source_with_source_id() -> None:
    async with async_session_factory() as session:
        session.add(build_memory(source_type="manual", source_id=uuid4()))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_agent_memory_rejects_automatic_source_without_source_id() -> None:
    async with async_session_factory() as session:
        session.add(build_memory(source_type="consolidation", source_id=None))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_agent_memory_allows_past_expiry() -> None:
    async with async_session_factory() as session:
        memory = build_memory(expires_at=datetime(2020, 1, 1, tzinfo=UTC))
        session.add(memory)
        await session.commit()

    assert memory.expires_at is not None
