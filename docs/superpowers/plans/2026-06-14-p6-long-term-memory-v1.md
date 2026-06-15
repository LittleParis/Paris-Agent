# P6 Long-Term Memory V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PostgreSQL-backed long-term memory V1 with owned CRUD, exact deduplication, optimistic locking, deterministic retrieval, controlled Skill policies, Mock Run read/write integration, and a Vue memory management page.

**Architecture:** PostgreSQL remains the source of truth. `MemoryManager` owns writes and lifecycle changes, `MemoryRepository` owns user-scoped persistence, `MemoryRetriever` owns deterministic scoring, and `MockMemoryExtractor` provides the only automatic write path through `memory_consolidation`. Milvus fields are stored as projection metadata but remain `not_indexed` throughout P6.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL, SQLite test adapter, pytest, Vue 3, TypeScript, Pinia, Axios, Element Plus, pnpm.

---

## Execution Preconditions

The current worktree contains uncommitted P5 implementation files. Before executing P6:

1. Finish and verify P5.
2. Commit P5 separately.
3. Start P6 from that clean P5 baseline.
4. Do not include unrelated working-tree changes in any P6 commit.

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest
Set-Location ..\frontend
pnpm build
Set-Location ..
git status --short
```

Expected:

```text
All backend tests pass.
The frontend build exits with code 0.
git status --short is empty before P6 implementation starts.
```

## File Responsibility Map

### Backend domain and persistence

- `backend/app/db/models/agent_memory.py`: Memory persistence model and database-facing constants.
- `backend/alembic/versions/20260614_0004_create_agent_memories.py`: PostgreSQL schema, constraints, indexes, and downgrade.
- `backend/app/schemas/memory.py`: API, command, pagination, and retrieval response contracts.
- `backend/app/memory/deduplicator.py`: Content/tag normalization and SHA-256 hash generation.
- `backend/app/db/repositories/memories.py`: User-scoped persistence, pagination, optimistic writes, and candidate queries.
- `backend/app/memory/manager.py`: Memory lifecycle orchestration and domain errors.
- `backend/app/memory/retriever.py`: Deterministic filtering, scoring, sorting, and access-stat updates.
- `backend/app/memory/extractor.py`: Deterministic `memory_consolidation` parser.
- `backend/app/api/routes_memories.py`: HTTP delivery layer.

### Skill and runtime integration

- `backend/app/schemas/skill.py`: Memory policy validation.
- `backend/app/skills/definitions/*.yaml`: Publish policy-bearing Skill versions.
- `backend/app/schemas/agent.py`: Memory Runtime Event contracts.
- `backend/app/agent/mock_runner.py`: Policy-driven memory read/write flow.

### Frontend

- `frontend/src/api/memories.ts`: Memory API types and calls.
- `frontend/src/pages/MemoryPage.vue`: Page-level query and editor orchestration.
- `frontend/src/components/memory/MemoryList.vue`: Memory table/list and actions.
- `frontend/src/components/memory/MemoryEditor.vue`: Create/edit form and optimistic-lock payload.
- `frontend/src/api/agentEvents.ts`: Memory Runtime Event types.
- `frontend/src/stores/agentRun.ts`: Memory Runtime state.
- `frontend/src/components/chat/AgentRunPanel.vue`: Retrieved/written memory summary.

---

### Task 1: Add the Memory model and migration

**Files:**
- Create: `backend/app/db/models/agent_memory.py`
- Create: `backend/alembic/versions/20260614_0004_create_agent_memories.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/alembic/env.py`
- Test: `backend/tests/test_memory_model.py`

- [ ] **Step 1: Write the failing model tests**

Create `backend/tests/test_memory_model.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.models.agent_memory import AgentMemory
from app.db.session import async_session_factory, engine


@pytest.fixture(autouse=True)
async def database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


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
        "source_detail": {"created_via": "memory_api"},
        "tags": ["index", "postgresql"],
        "content_hash": "a" * 64,
        "version": 1,
        "access_count": 0,
        "sync_status": "not_indexed",
    }
    values.update(overrides)
    return AgentMemory(**values)


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
    assert memory.version == 1
    assert memory.sync_status == "not_indexed"
    assert memory.external_vector_id is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memory_type", "unknown"),
        ("scope", "workspace"),
        ("importance", Decimal("1.1000")),
        ("confidence", Decimal("-0.1000")),
        ("version", 0),
        ("access_count", -1),
        ("source_type", "chat"),
        ("sync_status", "indexed"),
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
```

- [ ] **Step 2: Run the model tests and verify they fail**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_model.py -v
```

Expected:

```text
Collection fails with ModuleNotFoundError: No module named 'app.db.models.agent_memory'.
```

- [ ] **Step 3: Create the complete SQLAlchemy model**

Create `backend/app/db/models/agent_memory.py`:

```python
"""Long-term memory persistence model."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


MEMORY_TYPES = (
    "short_term",
    "learning_profile",
    "semantic",
    "episodic",
    "project",
    "procedural",
    "task",
    "runtime",
)

MEMORY_SCOPES = ("user", "project")
MEMORY_SOURCE_TYPES = ("manual", "agent_run", "consolidation")
MEMORY_SYNC_STATUSES = (
    "not_indexed",
    "pending",
    "syncing",
    "succeeded",
    "failed",
    "deleting",
    "deleted",
)


class AgentMemory(Base):
    """A user-owned long-term memory and its vector projection metadata."""

    __tablename__ = "agent_memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('short_term', 'learning_profile', 'semantic', "
            "'episodic', 'project', 'procedural', 'task', 'runtime')",
            name="ck_agent_memories_memory_type",
        ),
        CheckConstraint(
            "scope IN ('user', 'project')",
            name="ck_agent_memories_scope",
        ),
        CheckConstraint(
            "(scope = 'user' AND project_id IS NULL) OR "
            "(scope = 'project' AND project_id IS NOT NULL)",
            name="ck_agent_memories_scope_project",
        ),
        CheckConstraint(
            "memory_type <> 'project' OR scope = 'project'",
            name="ck_agent_memories_project_type_scope",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_agent_memories_content_not_blank",
        ),
        CheckConstraint(
            "summary IS NULL OR length(trim(summary)) > 0",
            name="ck_agent_memories_summary_not_blank",
        ),
        CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name="ck_agent_memories_importance",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_agent_memories_confidence",
        ),
        CheckConstraint(
            "source_type IN ('manual', 'agent_run', 'consolidation')",
            name="ck_agent_memories_source_type",
        ),
        CheckConstraint(
            "(source_type = 'manual' AND source_id IS NULL) OR "
            "(source_type IN ('agent_run', 'consolidation') "
            "AND source_id IS NOT NULL)",
            name="ck_agent_memories_source_id",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_agent_memories_content_hash_length",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_agent_memories_version",
        ),
        CheckConstraint(
            "access_count >= 0",
            name="ck_agent_memories_access_count",
        ),
        CheckConstraint(
            "sync_status IN ('not_indexed', 'pending', 'syncing', "
            "'succeeded', 'failed', 'deleting', 'deleted')",
            name="ck_agent_memories_sync_status",
        ),
        Index(
            "ix_agent_memories_user_type_updated",
            "user_id",
            "memory_type",
            text("updated_at DESC"),
        ),
        Index(
            "ix_agent_memories_user_updated",
            "user_id",
            text("updated_at DESC"),
        ),
        Index(
            "ix_agent_memories_project_updated",
            "project_id",
            text("updated_at DESC"),
            postgresql_where=text("project_id IS NOT NULL"),
            sqlite_where=text("project_id IS NOT NULL"),
        ),
        Index(
            "ix_agent_memories_user_expires",
            "user_id",
            "expires_at",
            postgresql_where=text(
                "expires_at IS NOT NULL AND deleted_at IS NULL"
            ),
            sqlite_where=text(
                "expires_at IS NOT NULL AND deleted_at IS NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    importance: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    source_detail: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    access_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    external_vector_id: Mapped[str | None] = mapped_column(Text)
    embedding_version: Mapped[str | None] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="not_indexed",
        server_default="not_indexed",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    sync_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

- [ ] **Step 4: Register the model**

Replace `backend/app/db/models/__init__.py` with:

```python
from app.db.models.agent_memory import AgentMemory
from app.db.models.agent_run import AgentRun
from app.db.models.agent_skill import AgentSkill
from app.db.models.agent_skill_run import AgentSkillRun
from app.db.models.agent_skill_version import AgentSkillVersion
from app.db.models.runtime_event import RuntimeEvent


__all__ = [
    "AgentMemory",
    "AgentRun",
    "AgentSkill",
    "AgentSkillRun",
    "AgentSkillVersion",
    "RuntimeEvent",
]
```

In `backend/alembic/env.py`, replace the model import block with:

```python
from app.db.models import (  # noqa: F401
    AgentMemory,
    AgentRun,
    AgentSkill,
    AgentSkillRun,
    AgentSkillVersion,
    RuntimeEvent,
)
```

- [ ] **Step 5: Create the complete Alembic migration**

Create `backend/alembic/versions/20260614_0004_create_agent_memories.py`:

```python
"""create agent_memories table

Revision ID: 20260614_0004
Revises: 20260614_0003
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260614_0004"
down_revision: str | None = "20260614_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("memory_type", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "importance",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
        ),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "source_detail",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "access_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("external_vector_id", sa.Text(), nullable=True),
        sa.Column("embedding_version", sa.Text(), nullable=True),
        sa.Column(
            "sync_status",
            sa.Text(),
            server_default=sa.text("'not_indexed'"),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "memory_type IN ('short_term', 'learning_profile', 'semantic', "
            "'episodic', 'project', 'procedural', 'task', 'runtime')",
            name="ck_agent_memories_memory_type",
        ),
        sa.CheckConstraint(
            "scope IN ('user', 'project')",
            name="ck_agent_memories_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'user' AND project_id IS NULL) OR "
            "(scope = 'project' AND project_id IS NOT NULL)",
            name="ck_agent_memories_scope_project",
        ),
        sa.CheckConstraint(
            "memory_type <> 'project' OR scope = 'project'",
            name="ck_agent_memories_project_type_scope",
        ),
        sa.CheckConstraint(
            "length(btrim(content)) > 0",
            name="ck_agent_memories_content_not_blank",
        ),
        sa.CheckConstraint(
            "summary IS NULL OR length(btrim(summary)) > 0",
            name="ck_agent_memories_summary_not_blank",
        ),
        sa.CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name="ck_agent_memories_importance",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_agent_memories_confidence",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'agent_run', 'consolidation')",
            name="ck_agent_memories_source_type",
        ),
        sa.CheckConstraint(
            "(source_type = 'manual' AND source_id IS NULL) OR "
            "(source_type IN ('agent_run', 'consolidation') "
            "AND source_id IS NOT NULL)",
            name="ck_agent_memories_source_id",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_detail) = 'object'",
            name="ck_agent_memories_source_detail_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(tags) = 'array'",
            name="ck_agent_memories_tags_array",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_agent_memories_content_hash",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_agent_memories_version",
        ),
        sa.CheckConstraint(
            "access_count >= 0",
            name="ck_agent_memories_access_count",
        ),
        sa.CheckConstraint(
            "sync_status IN ('not_indexed', 'pending', 'syncing', "
            "'succeeded', 'failed', 'deleting', 'deleted')",
            name="ck_agent_memories_sync_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "memory_id",
            name="uq_agent_memories_memory_id",
        ),
    )
    op.create_index(
        "ix_agent_memories_user_type_updated",
        "agent_memories",
        ["user_id", "memory_type", sa.literal_column("updated_at DESC")],
    )
    op.create_index(
        "ix_agent_memories_user_updated",
        "agent_memories",
        ["user_id", sa.literal_column("updated_at DESC")],
    )
    op.create_index(
        "ix_agent_memories_project_updated",
        "agent_memories",
        ["project_id", sa.literal_column("updated_at DESC")],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "ix_agent_memories_user_expires",
        "agent_memories",
        ["user_id", "expires_at"],
        postgresql_where=sa.text(
            "expires_at IS NOT NULL AND deleted_at IS NULL"
        ),
    )
    op.create_index(
        "uq_agent_memories_active_content",
        "agent_memories",
        [
            "user_id",
            "scope",
            sa.literal_column(
                "coalesce(project_id, "
                "'00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            "memory_type",
            "content_hash",
        ],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_agent_memories_active_content",
        table_name="agent_memories",
    )
    op.drop_index(
        "ix_agent_memories_user_expires",
        table_name="agent_memories",
    )
    op.drop_index(
        "ix_agent_memories_project_updated",
        table_name="agent_memories",
    )
    op.drop_index(
        "ix_agent_memories_user_updated",
        table_name="agent_memories",
    )
    op.drop_index(
        "ix_agent_memories_user_type_updated",
        table_name="agent_memories",
    )
    op.drop_table("agent_memories")
```

- [ ] **Step 6: Run the model tests**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_model.py -v
```

Expected:

```text
All tests in test_memory_model.py pass.
```

- [ ] **Step 7: Verify the PostgreSQL migration**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run alembic upgrade head
uv run alembic downgrade 20260614_0003
uv run alembic upgrade head
```

Expected:

```text
Upgrade, downgrade, and re-upgrade all exit with code 0.
The P5 tables remain present after downgrade to 20260614_0003.
```

- [ ] **Step 8: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/db/models/agent_memory.py backend/app/db/models/__init__.py backend/alembic/env.py backend/alembic/versions/20260614_0004_create_agent_memories.py backend/tests/test_memory_model.py
git commit -m "feat(memory): add agent memories schema"
```

---

### Task 2: Add Memory schemas and exact deduplication

**Files:**
- Create: `backend/app/schemas/memory.py`
- Create: `backend/app/memory/deduplicator.py`
- Modify: `backend/app/memory/__init__.py`
- Test: `backend/tests/test_memory_deduplicator.py`
- Test: `backend/tests/test_memory_schemas.py`

- [ ] **Step 1: Write the failing deduplicator tests**

Create `backend/tests/test_memory_deduplicator.py`:

```python
from uuid import UUID

from app.memory.deduplicator import (
    compute_content_hash,
    normalize_content,
    normalize_tags,
)


def test_normalize_content_uses_nfkc_and_collapses_whitespace() -> None:
    assert normalize_content("  ＰｏｓｔｇｒｅＳＱＬ\n\t索引  ") == "PostgreSQL 索引"


def test_normalize_content_preserves_case_and_punctuation() -> None:
    assert normalize_content("Path C:\\Temp\\A.py") == "Path C:\\Temp\\A.py"


def test_normalize_tags_trims_deduplicates_and_sorts() -> None:
    assert normalize_tags([" postgres ", "Index", "postgres"]) == [
        "Index",
        "postgres",
    ]


def test_content_hash_changes_with_scope_and_project() -> None:
    project_id = UUID("11111111-1111-1111-1111-111111111111")
    user_hash = compute_content_hash(
        memory_type="semantic",
        scope="user",
        project_id=None,
        content="PostgreSQL index",
    )
    project_hash = compute_content_hash(
        memory_type="semantic",
        scope="project",
        project_id=project_id,
        content="PostgreSQL index",
    )

    assert len(user_hash) == 64
    assert user_hash != project_hash
```

- [ ] **Step 2: Write the failing schema tests**

Create `backend/tests/test_memory_schemas.py`:

```python
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.memory import MemoryCreate, MemoryUpdate


def test_memory_create_normalizes_tags() -> None:
    payload = MemoryCreate(
        memory_type="learning_profile",
        scope="user",
        project_id=None,
        content="Learning PostgreSQL",
        summary=None,
        importance=Decimal("0.8"),
        confidence=Decimal("0.9"),
        tags=[" postgres ", "index", "postgres"],
        expires_at=None,
    )

    assert payload.tags == ["index", "postgres"]


def test_memory_create_rejects_project_scope_without_project_id() -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(
            memory_type="project",
            scope="project",
            project_id=None,
            content="Architecture decision",
            importance=Decimal("0.8"),
            confidence=Decimal("0.9"),
            tags=[],
        )


def test_memory_create_rejects_user_scope_with_project_id() -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(
            memory_type="semantic",
            scope="user",
            project_id=uuid4(),
            content="Architecture decision",
            importance=Decimal("0.8"),
            confidence=Decimal("0.9"),
            tags=[],
        )


def test_memory_update_requires_at_least_one_mutation() -> None:
    with pytest.raises(ValidationError):
        MemoryUpdate(version=1)
```

- [ ] **Step 3: Run the tests and verify they fail**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_deduplicator.py tests/test_memory_schemas.py -v
```

Expected:

```text
Collection fails because app.schemas.memory and app.memory.deduplicator do not exist.
```

- [ ] **Step 4: Create the complete deduplicator**

Create `backend/app/memory/deduplicator.py`:

```python
"""Deterministic normalization and exact memory deduplication."""

import hashlib
import unicodedata
from uuid import UUID


def normalize_content(value: str) -> str:
    """Normalize Unicode and whitespace without changing case or punctuation."""

    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().split())


def normalize_tags(tags: list[str]) -> list[str]:
    """Trim, remove empty values, deduplicate, and sort tags."""

    normalized = {
        unicodedata.normalize("NFKC", tag).strip()
        for tag in tags
        if unicodedata.normalize("NFKC", tag).strip()
    }
    return sorted(normalized)


def compute_content_hash(
    *,
    memory_type: str,
    scope: str,
    project_id: UUID | None,
    content: str,
) -> str:
    """Hash the exact active-memory identity."""

    canonical = "\n".join(
        [
            memory_type,
            scope,
            str(project_id) if project_id is not None else "",
            normalize_content(content),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Create the complete Pydantic schemas**

Create `backend/app/schemas/memory.py`:

```python
"""Long-term memory request, response, and retrieval contracts."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.memory.deduplicator import normalize_content, normalize_tags


MemoryType = Literal[
    "short_term",
    "learning_profile",
    "semantic",
    "episodic",
    "project",
    "procedural",
    "task",
    "runtime",
]
MemoryScope = Literal["user", "project"]
MemorySourceType = Literal["manual", "agent_run", "consolidation"]
MemorySyncStatus = Literal[
    "not_indexed",
    "pending",
    "syncing",
    "succeeded",
    "failed",
    "deleting",
    "deleted",
]


class MemoryFields(BaseModel):
    """Shared mutable memory fields."""

    memory_type: MemoryType
    scope: MemoryScope
    project_id: uuid.UUID | None = None
    content: str = Field(min_length=1)
    summary: str | None = None
    importance: Decimal = Field(ge=0, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list, max_length=20)
    expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        tags = normalize_tags(value)
        if len(tags) > 20:
            raise ValueError("tags must contain at most 20 values")
        if any(len(tag) > 64 for tag in tags):
            raise ValueError("each tag must contain at most 64 characters")
        return tags

    @model_validator(mode="after")
    def validate_scope(self) -> "MemoryFields":
        if self.scope == "user" and self.project_id is not None:
            raise ValueError("project_id must be null for user scope")
        if self.scope == "project" and self.project_id is None:
            raise ValueError("project_id is required for project scope")
        if self.memory_type == "project" and self.scope != "project":
            raise ValueError("project memories must use project scope")
        return self


class MemoryCreate(MemoryFields):
    """Manual memory creation request."""


class MemoryUpdate(BaseModel):
    """Optimistic partial memory update."""

    version: int = Field(ge=1)
    memory_type: MemoryType | None = None
    scope: MemoryScope | None = None
    project_id: uuid.UUID | None = None
    content: str | None = None
    summary: str | None = None
    importance: Decimal | None = Field(default=None, ge=0, le=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    tags: list[str] | None = None
    expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        tags = normalize_tags(value)
        if len(tags) > 20:
            raise ValueError("tags must contain at most 20 values")
        if any(len(tag) > 64 for tag in tags):
            raise ValueError("each tag must contain at most 64 characters")
        return tags

    @model_validator(mode="after")
    def require_mutation(self) -> "MemoryUpdate":
        fields = self.model_fields_set - {"version"}
        if not fields:
            raise ValueError("at least one mutable field is required")
        return self


class MemoryRead(BaseModel):
    """Public memory resource."""

    model_config = ConfigDict(from_attributes=True)

    memory_id: uuid.UUID
    project_id: uuid.UUID | None
    memory_type: MemoryType
    scope: MemoryScope
    content: str
    summary: str | None
    importance: Decimal
    confidence: Decimal
    source_type: MemorySourceType
    source_id: uuid.UUID | None
    source_detail: dict
    tags: list[str]
    version: int
    access_count: int
    last_accessed_at: datetime | None
    expires_at: datetime | None
    sync_status: MemorySyncStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("importance", "confidence")
    def serialize_score(self, value: Decimal) -> str:
        return f"{value:.4f}"


class MemoryListResponse(BaseModel):
    items: list[MemoryRead]
    next_cursor: str | None


class MemorySearchRequest(BaseModel):
    query: str = ""
    memory_types: list[MemoryType] = Field(default_factory=list)
    project_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return normalize_content(value)

    @field_validator("tags")
    @classmethod
    def normalize_search_tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)


class MemoryScoreBreakdown(BaseModel):
    text_match: float
    importance: float
    confidence: float
    recency: float
    access_weight: float
    project_relevance: float


class MemorySearchHit(BaseModel):
    memory: MemoryRead
    score: float
    score_breakdown: MemoryScoreBreakdown


class MemorySearchResponse(BaseModel):
    items: list[MemorySearchHit]


class ConsolidationMemoryCommand(MemoryFields):
    """Validated deterministic extractor output."""


class MemoryWriteResult(BaseModel):
    memory: MemoryRead
    created: bool
    deduplicated: bool
```

Replace `backend/app/memory/__init__.py` with:

```python
"""Long-term memory domain services."""

from app.memory.deduplicator import (
    compute_content_hash,
    normalize_content,
    normalize_tags,
)


__all__ = [
    "compute_content_hash",
    "normalize_content",
    "normalize_tags",
]
```

- [ ] **Step 6: Run the schema and deduplicator tests**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_deduplicator.py tests/test_memory_schemas.py -v
```

Expected:

```text
All tests pass.
```

- [ ] **Step 7: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/schemas/memory.py backend/app/memory/deduplicator.py backend/app/memory/__init__.py backend/tests/test_memory_deduplicator.py backend/tests/test_memory_schemas.py
git commit -m "feat(memory): add memory contracts and deduplication"
```

---

### Task 3: Add the user-scoped Memory repository

**Files:**
- Create: `backend/app/db/repositories/memories.py`
- Modify: `backend/app/db/repositories/__init__.py`
- Test: `backend/tests/test_memory_repository.py`

- [ ] **Step 1: Write the failing repository tests**

Create `backend/tests/test_memory_repository.py`:

```python
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
```

- [ ] **Step 2: Run the repository tests and verify they fail**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_repository.py -v
```

Expected:

```text
Collection fails with ModuleNotFoundError: No module named 'app.db.repositories.memories'.
```

- [ ] **Step 3: Create the complete repository**

Create `backend/app/db/repositories/memories.py`:

```python
"""User-scoped long-term memory persistence."""

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_memory import AgentMemory


def _encode_cursor(updated_at: datetime, memory_id: uuid.UUID) -> str:
    payload = json.dumps(
        {
            "updated_at": updated_at.isoformat(),
            "memory_id": str(memory_id),
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        return (
            datetime.fromisoformat(payload["updated_at"]),
            uuid.UUID(payload["memory_id"]),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid memory cursor") from exc


class MemoryRepository:
    """Persist memories without deciding domain policy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        memory_type: str,
        scope: str,
        content: str,
        summary: str | None,
        importance: Decimal,
        confidence: Decimal,
        source_type: str,
        source_id: uuid.UUID | None,
        source_detail: dict,
        tags: list[str],
        content_hash: str,
        expires_at: datetime | None,
    ) -> AgentMemory:
        memory = AgentMemory(
            memory_id=uuid.uuid4(),
            user_id=user_id,
            project_id=project_id,
            memory_type=memory_type,
            scope=scope,
            content=content,
            summary=summary,
            importance=importance,
            confidence=confidence,
            source_type=source_type,
            source_id=source_id,
            source_detail=source_detail,
            tags=tags,
            content_hash=content_hash,
            version=1,
            access_count=0,
            sync_status="not_indexed",
            expires_at=expires_at,
        )
        self.session.add(memory)
        await self.session.flush()
        await self.session.refresh(memory)
        return memory

    async def get_owned(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> AgentMemory | None:
        stmt = select(AgentMemory).where(
            AgentMemory.memory_id == memory_id,
            AgentMemory.user_id == user_id,
        )
        if not include_deleted:
            stmt = stmt.where(AgentMemory.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active_duplicate(
        self,
        *,
        user_id: uuid.UUID,
        scope: str,
        project_id: uuid.UUID | None,
        memory_type: str,
        content_hash: str,
        exclude_memory_id: uuid.UUID | None = None,
    ) -> AgentMemory | None:
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.scope == scope,
            AgentMemory.memory_type == memory_type,
            AgentMemory.content_hash == content_hash,
            AgentMemory.deleted_at.is_(None),
        )
        if project_id is None:
            stmt = stmt.where(AgentMemory.project_id.is_(None))
        else:
            stmt = stmt.where(AgentMemory.project_id == project_id)
        if exclude_memory_id is not None:
            stmt = stmt.where(AgentMemory.memory_id != exclude_memory_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        *,
        user_id: uuid.UUID,
        memory_type: str | None,
        scope: str | None,
        project_id: uuid.UUID | None,
        tag: str | None,
        include_expired: bool,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[AgentMemory], str | None]:
        now = datetime.now(UTC)
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.deleted_at.is_(None),
        )
        if not include_expired:
            stmt = stmt.where(
                or_(
                    AgentMemory.expires_at.is_(None),
                    AgentMemory.expires_at > now,
                )
            )
        if memory_type is not None:
            stmt = stmt.where(AgentMemory.memory_type == memory_type)
        if scope is not None:
            stmt = stmt.where(AgentMemory.scope == scope)
        if project_id is not None:
            stmt = stmt.where(AgentMemory.project_id == project_id)
        if cursor is not None:
            cursor_time, cursor_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    AgentMemory.updated_at < cursor_time,
                    and_(
                        AgentMemory.updated_at == cursor_time,
                        AgentMemory.memory_id > cursor_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            AgentMemory.updated_at.desc(),
            AgentMemory.memory_id.asc(),
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if tag is not None:
            rows = [memory for memory in rows if tag in memory.tags]
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = _encode_cursor(last.updated_at, last.memory_id)
        return page, next_cursor

    async def search_candidates(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        memory_types: list[str],
        tags: list[str],
    ) -> list[AgentMemory]:
        now = datetime.now(UTC)
        scope_filter = AgentMemory.scope == "user"
        if project_id is not None:
            scope_filter = or_(
                AgentMemory.scope == "user",
                and_(
                    AgentMemory.scope == "project",
                    AgentMemory.project_id == project_id,
                ),
            )
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.deleted_at.is_(None),
            or_(
                AgentMemory.expires_at.is_(None),
                AgentMemory.expires_at > now,
            ),
            scope_filter,
        )
        if memory_types:
            stmt = stmt.where(AgentMemory.memory_type.in_(memory_types))
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if tags:
            required = set(tags)
            rows = [
                memory
                for memory in rows
                if required.issubset(set(memory.tags))
            ]
        return rows

    async def update_owned_with_version(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        expected_version: int,
        values: dict,
    ) -> bool:
        values = {
            **values,
            "version": AgentMemory.version + 1,
            "updated_at": datetime.now(UTC),
        }
        result = await self.session.execute(
            update(AgentMemory)
            .where(
                AgentMemory.memory_id == memory_id,
                AgentMemory.user_id == user_id,
                AgentMemory.version == expected_version,
                AgentMemory.deleted_at.is_(None),
            )
            .values(**values)
        )
        return result.rowcount == 1

    async def soft_delete_owned_with_version(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        expected_version: int,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(AgentMemory)
            .where(
                AgentMemory.memory_id == memory_id,
                AgentMemory.user_id == user_id,
                AgentMemory.version == expected_version,
                AgentMemory.deleted_at.is_(None),
            )
            .values(
                deleted_at=now,
                updated_at=now,
                version=AgentMemory.version + 1,
            )
        )
        return result.rowcount == 1

    async def touch_access_batch(
        self,
        *,
        user_id: uuid.UUID,
        memory_ids: list[uuid.UUID],
    ) -> None:
        if not memory_ids:
            return
        await self.session.execute(
            update(AgentMemory)
            .where(
                AgentMemory.user_id == user_id,
                AgentMemory.memory_id.in_(memory_ids),
                AgentMemory.deleted_at.is_(None),
            )
            .values(
                access_count=AgentMemory.access_count + 1,
                last_accessed_at=datetime.now(UTC),
            )
        )
```

- [ ] **Step 4: Export the repository**

Replace `backend/app/db/repositories/__init__.py` with:

```python
from app.db.repositories.agent_runs import AgentRunRepository
from app.db.repositories.memories import MemoryRepository
from app.db.repositories.runtime_events import RuntimeEventRepository
from app.db.repositories.skills import (
    AgentSkillRunRepository,
    SkillRepository,
    SkillVersionRepository,
)


__all__ = [
    "AgentRunRepository",
    "AgentSkillRunRepository",
    "MemoryRepository",
    "RuntimeEventRepository",
    "SkillRepository",
    "SkillVersionRepository",
]
```

- [ ] **Step 5: Run the repository tests**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_repository.py -v
```

Expected:

```text
All repository tests pass.
```

- [ ] **Step 6: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/db/repositories/memories.py backend/app/db/repositories/__init__.py backend/tests/test_memory_repository.py
git commit -m "feat(memory): add owned memory repository"
```

---

### Task 4: Add MemoryManager lifecycle orchestration

**Files:**
- Create: `backend/app/memory/manager.py`
- Test: `backend/tests/test_memory_manager.py`

- [ ] **Step 1: Write the failing manager tests**

Create `backend/tests/test_memory_manager.py`:

```python
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
```

- [ ] **Step 2: Run the manager tests and verify they fail**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_manager.py -v
```

Expected:

```text
Collection fails with ModuleNotFoundError: No module named 'app.memory.manager'.
```

- [ ] **Step 3: Create the complete MemoryManager**

Create `backend/app/memory/manager.py`:

```python
"""Long-term memory lifecycle orchestration."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_memory import AgentMemory
from app.db.repositories.memories import MemoryRepository
from app.memory.deduplicator import compute_content_hash
from app.schemas.memory import (
    ConsolidationMemoryCommand,
    MemoryCreate,
    MemoryRead,
    MemoryUpdate,
    MemoryWriteResult,
)


class MemoryDomainError(Exception):
    """Base memory domain error."""


class MemoryNotFoundError(MemoryDomainError):
    """The owned active memory does not exist."""


class DuplicateMemoryError(MemoryDomainError):
    """An active exact duplicate exists."""

    def __init__(self, memory_id: uuid.UUID) -> None:
        self.memory_id = memory_id
        super().__init__("An active duplicate memory already exists.")


class MemoryVersionConflictError(MemoryDomainError):
    """The optimistic-lock version is stale."""

    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__("Memory version conflict.")


def _content_hash(
    *,
    memory_type: str,
    scope: str,
    project_id: uuid.UUID | None,
    content: str,
) -> str:
    return compute_content_hash(
        memory_type=memory_type,
        scope=scope,
        project_id=project_id,
        content=content,
    )


class MemoryManager:
    """The only write entry point for memory lifecycle changes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MemoryRepository(session)

    async def get(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AgentMemory:
        memory = await self.repository.get_owned(memory_id, user_id)
        if memory is None:
            raise MemoryNotFoundError
        return memory

    async def create_manual(
        self,
        *,
        user_id: uuid.UUID,
        payload: MemoryCreate,
    ) -> AgentMemory:
        content_hash = _content_hash(
            memory_type=payload.memory_type,
            scope=payload.scope,
            project_id=payload.project_id,
            content=payload.content,
        )
        duplicate = await self.repository.find_active_duplicate(
            user_id=user_id,
            scope=payload.scope,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            content_hash=content_hash,
        )
        if duplicate is not None:
            raise DuplicateMemoryError(duplicate.memory_id)
        memory = await self.repository.create(
            user_id=user_id,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            scope=payload.scope,
            content=payload.content,
            summary=payload.summary,
            importance=payload.importance,
            confidence=payload.confidence,
            source_type="manual",
            source_id=None,
            source_detail={"created_via": "memory_api"},
            tags=payload.tags,
            content_hash=content_hash,
            expires_at=payload.expires_at,
        )
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def create_consolidated(
        self,
        *,
        user_id: uuid.UUID,
        run_id: uuid.UUID,
        skill_version: str,
        payload: ConsolidationMemoryCommand | MemoryCreate,
    ) -> MemoryWriteResult:
        content_hash = _content_hash(
            memory_type=payload.memory_type,
            scope=payload.scope,
            project_id=payload.project_id,
            content=payload.content,
        )
        duplicate = await self.repository.find_active_duplicate(
            user_id=user_id,
            scope=payload.scope,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            content_hash=content_hash,
        )
        if duplicate is not None:
            return MemoryWriteResult(
                memory=MemoryRead.model_validate(duplicate),
                created=False,
                deduplicated=True,
            )
        memory = await self.repository.create(
            user_id=user_id,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            scope=payload.scope,
            content=payload.content,
            summary=payload.summary,
            importance=payload.importance,
            confidence=payload.confidence,
            source_type="consolidation",
            source_id=run_id,
            source_detail={
                "skill_id": "memory_consolidation",
                "skill_version": skill_version,
                "extractor": "deterministic_v1",
            },
            tags=payload.tags,
            content_hash=content_hash,
            expires_at=payload.expires_at,
        )
        await self.session.commit()
        await self.session.refresh(memory)
        return MemoryWriteResult(
            memory=MemoryRead.model_validate(memory),
            created=True,
            deduplicated=False,
        )

    async def update(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: MemoryUpdate,
    ) -> AgentMemory:
        current = await self.get(memory_id=memory_id, user_id=user_id)
        if current.version != payload.version:
            raise MemoryVersionConflictError(current.version)

        values = payload.model_dump(
            exclude={"version"},
            exclude_unset=True,
        )
        merged = {
            "memory_type": values.get("memory_type", current.memory_type),
            "scope": values.get("scope", current.scope),
            "project_id": (
                values["project_id"]
                if "project_id" in values
                else current.project_id
            ),
            "content": values.get("content", current.content),
        }
        if merged["scope"] == "user" and merged["project_id"] is not None:
            raise ValueError("project_id must be null for user scope")
        if merged["scope"] == "project" and merged["project_id"] is None:
            raise ValueError("project_id is required for project scope")
        if (
            merged["memory_type"] == "project"
            and merged["scope"] != "project"
        ):
            raise ValueError("project memories must use project scope")

        content_hash = _content_hash(**merged)
        duplicate = await self.repository.find_active_duplicate(
            user_id=user_id,
            scope=merged["scope"],
            project_id=merged["project_id"],
            memory_type=merged["memory_type"],
            content_hash=content_hash,
            exclude_memory_id=memory_id,
        )
        if duplicate is not None:
            raise DuplicateMemoryError(duplicate.memory_id)
        values["content_hash"] = content_hash
        updated = await self.repository.update_owned_with_version(
            memory_id=memory_id,
            user_id=user_id,
            expected_version=payload.version,
            values=values,
        )
        if not updated:
            latest = await self.repository.get_owned(memory_id, user_id)
            if latest is None:
                raise MemoryNotFoundError
            raise MemoryVersionConflictError(latest.version)
        await self.session.commit()
        memory = await self.repository.get_owned(memory_id, user_id)
        if memory is None:
            raise MemoryNotFoundError
        return memory

    async def delete(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        version: int,
    ) -> None:
        current = await self.get(memory_id=memory_id, user_id=user_id)
        if current.version != version:
            raise MemoryVersionConflictError(current.version)
        deleted = await self.repository.soft_delete_owned_with_version(
            memory_id=memory_id,
            user_id=user_id,
            expected_version=version,
        )
        if not deleted:
            latest = await self.repository.get_owned(memory_id, user_id)
            if latest is None:
                raise MemoryNotFoundError
            raise MemoryVersionConflictError(latest.version)
        await self.session.commit()
```

- [ ] **Step 4: Run the manager tests**

Run:

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_manager.py -v
```

Expected:

```text
All manager tests pass.
```

- [ ] **Step 5: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/memory/manager.py backend/tests/test_memory_manager.py
git commit -m "feat(memory): add memory lifecycle manager"
```

### Task 5: Add deterministic memory retrieval

**Files:**
- Create: `backend/app/memory/retriever.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_memory_retriever.py`

- [ ] **Step 1: Write the failing retriever tests**

Create `backend/tests/test_memory_retriever.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.repositories.memories import MemoryRepository
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


@pytest.mark.asyncio
async def test_search_ranks_text_and_project_match_first(db_session) -> None:
    user_id = uuid4()
    project_id = uuid4()
    manager = MemoryManager(db_session)
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
        repository=MemoryRepository(db_session),
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


@pytest.mark.asyncio
async def test_runtime_search_updates_access_statistics(db_session) -> None:
    user_id = uuid4()
    manager = MemoryManager(db_session)
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
        repository=MemoryRepository(db_session),
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
    refreshed = await MemoryRepository(db_session).get_owned(
        memory.memory_id,
        user_id,
    )

    assert refreshed is not None
    assert refreshed.access_count == 1
    assert refreshed.last_accessed_at is not None


def test_recency_score_decays_monotonically() -> None:
    now = datetime.now(UTC)

    recent = MemoryRetriever.recency_score(now - timedelta(hours=1), now)
    old = MemoryRetriever.recency_score(now - timedelta(days=60), now)

    assert 0 <= old < recent <= 1
```

- [ ] **Step 2: Run the test and confirm the missing module**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_retriever.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'app.memory.retriever'
```

- [ ] **Step 3: Add retrieval weights to settings**

Replace `backend/app/core/config.py` with:

```python
from functools import lru_cache
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    service_name: str
    environment: str
    api_host: str
    api_port: int
    database_url: str
    redis_url: str
    rabbitmq_url: str
    default_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    mock_run_step_delay_seconds: float = 0.01
    sse_heartbeat_seconds: float = 15.0
    memory_text_weight: float = Field(default=0.40, ge=0)
    memory_importance_weight: float = Field(default=0.20, ge=0)
    memory_confidence_weight: float = Field(default=0.10, ge=0)
    memory_recency_weight: float = Field(default=0.10, ge=0)
    memory_access_weight: float = Field(default=0.05, ge=0)
    memory_project_weight: float = Field(default=0.15, ge=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_memory_weights(self) -> "Settings":
        if self.memory_weight_total <= 0:
            raise ValueError("at least one memory weight must be positive")
        return self

    @property
    def memory_weight_total(self) -> float:
        return (
            self.memory_text_weight
            + self.memory_importance_weight
            + self.memory_confidence_weight
            + self.memory_recency_weight
            + self.memory_access_weight
            + self.memory_project_weight
        )

    def normalized_memory_weights(self) -> dict[str, float]:
        total = self.memory_weight_total
        return {
            "text_match": self.memory_text_weight / total,
            "importance": self.memory_importance_weight / total,
            "confidence": self.memory_confidence_weight / total,
            "recency": self.memory_recency_weight / total,
            "access_weight": self.memory_access_weight / total,
            "project_relevance": self.memory_project_weight / total,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Append to `backend/.env.example`:

```dotenv
MEMORY_TEXT_WEIGHT=0.40
MEMORY_IMPORTANCE_WEIGHT=0.20
MEMORY_CONFIDENCE_WEIGHT=0.10
MEMORY_RECENCY_WEIGHT=0.10
MEMORY_ACCESS_WEIGHT=0.05
MEMORY_PROJECT_WEIGHT=0.15
```

- [ ] **Step 4: Implement the retriever**

Create `backend/app/memory/retriever.py`:

```python
from __future__ import annotations

import math
import re
import uuid
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.db.models.agent_memory import AgentMemory
from app.db.repositories.memories import MemoryRepository
from app.schemas.memory import (
    MemoryRead,
    MemoryScoreBreakdown,
    MemorySearchHit,
)

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


class MemoryRetriever:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        project_id: uuid.UUID | None,
        memory_types: list[str],
        tags: list[str],
        limit: int,
        touch_access: bool,
    ) -> list[MemorySearchHit]:
        candidates = await self.repository.search_candidates(
            user_id=user_id,
            project_id=project_id,
            memory_types=memory_types,
            tags=tags,
        )
        now = datetime.now(UTC)
        hits = [
            self._score(
                memory=memory,
                query=query,
                project_id=project_id,
                now=now,
            )
            for memory in candidates
        ]
        hits.sort(
            key=lambda hit: (
                hit.score,
                float(hit.memory.importance),
                hit.memory.updated_at,
                str(hit.memory.memory_id),
            ),
            reverse=True,
        )
        selected = hits[:limit]
        if touch_access and selected:
            await self.repository.touch_access_batch(
                user_id=user_id,
                memory_ids=[hit.memory.memory_id for hit in selected],
            )
            await self.repository.session.commit()
        return selected

    def _score(
        self,
        *,
        memory: AgentMemory,
        query: str,
        project_id: uuid.UUID | None,
        now: datetime,
    ) -> MemorySearchHit:
        breakdown = MemoryScoreBreakdown(
            text_match=self.text_match(query, self._searchable_text(memory)),
            importance=float(memory.importance),
            confidence=float(memory.confidence),
            recency=self.recency_score(memory.updated_at, now),
            access_weight=self.access_score(memory.access_count),
            project_relevance=self.project_score(
                memory.project_id,
                project_id,
            ),
        )
        weights = self.settings.normalized_memory_weights()
        score = sum(
            getattr(breakdown, name) * weight
            for name, weight in weights.items()
        )
        return MemorySearchHit(
            memory=MemoryRead.model_validate(memory),
            score=round(score, 6),
            score_breakdown=breakdown,
        )

    @staticmethod
    def text_match(query: str, content: str) -> float:
        query_tokens = set(TOKEN_PATTERN.findall(query.casefold()))
        content_tokens = set(TOKEN_PATTERN.findall(content.casefold()))
        if not query_tokens:
            return 1.0
        if not content_tokens:
            return 0.0
        return len(query_tokens & content_tokens) / len(query_tokens)

    @staticmethod
    def recency_score(updated_at: datetime, now: datetime) -> float:
        value = (
            updated_at.replace(tzinfo=UTC)
            if updated_at.tzinfo is None
            else updated_at.astimezone(UTC)
        )
        age_days = max((now - value).total_seconds() / 86400, 0)
        return math.exp(-age_days / 30)

    @staticmethod
    def access_score(access_count: int) -> float:
        return min(math.log1p(max(access_count, 0)) / math.log(11), 1.0)

    @staticmethod
    def project_score(
        memory_project_id: uuid.UUID | None,
        requested_project_id: uuid.UUID | None,
    ) -> float:
        if requested_project_id and memory_project_id == requested_project_id:
            return 1.0
        if memory_project_id is None:
            return 0.5
        return 0.0

    @staticmethod
    def _searchable_text(memory: AgentMemory) -> str:
        return " ".join(
            [
                memory.summary or "",
                memory.content,
                " ".join(memory.tags),
            ]
        )
```

- [ ] **Step 5: Run the focused tests**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_retriever.py -v
```

Expected:

```text
All retriever tests pass.
```

- [ ] **Step 6: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/core/config.py backend/.env.example backend/app/memory/retriever.py backend/tests/test_memory_retriever.py
git commit -m "feat(memory): add deterministic retrieval"
```

### Task 6: Add the deterministic consolidation extractor

**Files:**
- Create: `backend/app/memory/extractor.py`
- Test: `backend/tests/test_memory_extractor.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_memory_extractor.py`:

```python
from uuid import uuid4

from app.memory.extractor import MockMemoryExtractor


def test_explicit_project_fact_becomes_project_memory() -> None:
    project_id = uuid4()
    run_id = uuid4()

    commands = MockMemoryExtractor().extract(
        text="Remember that Paris Agent uses Milvus in P7.",
        project_id=project_id,
        run_id=run_id,
    )

    assert len(commands) == 1
    assert commands[0].memory_type == "project"
    assert commands[0].scope == "project"
    assert commands[0].project_id == project_id
    assert commands[0].source_detail == {
        "rule": "explicit_remember",
        "run_id": str(run_id),
    }


def test_learning_preference_becomes_user_memory() -> None:
    commands = MockMemoryExtractor().extract(
        text="I prefer learning with small runnable examples.",
        project_id=None,
        run_id=uuid4(),
    )

    assert commands[0].memory_type == "learning_profile"
    assert commands[0].scope == "user"
    assert commands[0].project_id is None


def test_text_without_memory_signal_is_ignored() -> None:
    commands = MockMemoryExtractor().extract(
        text="Explain FastAPI dependency injection.",
        project_id=None,
        run_id=uuid4(),
    )

    assert commands == []
```

- [ ] **Step 2: Confirm the test fails**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_extractor.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'app.memory.extractor'
```

- [ ] **Step 3: Implement the complete extractor**

Create `backend/app/memory/extractor.py`:

```python
from __future__ import annotations

import re
import uuid
from decimal import Decimal

from app.schemas.memory import ConsolidationMemoryCommand

WHITESPACE = re.compile(r"\s+")
EXPLICIT_PATTERNS = (
    re.compile(r"^\s*remember(?:\s+that)?\s+(.+)$", re.IGNORECASE),
    re.compile(r"^\s*请记住[：:\s]*(.+)$"),
    re.compile(r"^\s*记住[：:\s]*(.+)$"),
)
LEARNING_PATTERNS = (
    re.compile(r"\bi prefer learning\b", re.IGNORECASE),
    re.compile(r"\bmy learning preference\b", re.IGNORECASE),
    re.compile(r"我(?:更)?喜欢(?:通过|用).+学习"),
    re.compile(r"我的学习偏好"),
)


class MockMemoryExtractor:
    def extract(
        self,
        *,
        text: str,
        project_id: uuid.UUID | None,
        run_id: uuid.UUID,
    ) -> list[ConsolidationMemoryCommand]:
        normalized = WHITESPACE.sub(" ", text).strip()
        if not normalized:
            return []

        explicit = self._explicit_content(normalized)
        learning = any(pattern.search(normalized) for pattern in LEARNING_PATTERNS)
        if explicit is None and not learning:
            return []

        content = explicit or normalized
        memory_type = (
            "learning_profile"
            if learning
            else "project"
            if project_id is not None
            else "semantic"
        )
        scope = "project" if project_id is not None else "user"
        tags = [memory_type]
        if project_id is not None:
            tags.append(str(project_id))

        return [
            ConsolidationMemoryCommand(
                memory_type=memory_type,
                scope=scope,
                project_id=project_id,
                content=content,
                summary=content[:240],
                importance=Decimal("0.7000"),
                confidence=Decimal("0.8500"),
                tags=tags,
                source_detail={
                    "rule": (
                        "learning_preference"
                        if learning
                        else "explicit_remember"
                    ),
                    "run_id": str(run_id),
                },
            )
        ]

    @staticmethod
    def _explicit_content(text: str) -> str | None:
        for pattern in EXPLICIT_PATTERNS:
            match = pattern.match(text)
            if match:
                return match.group(1).strip().rstrip(".。")
        return None
```

The extractor requires `source_detail` only on consolidation commands. Replace `ConsolidationMemoryCommand` in `backend/app/schemas/memory.py` with:

```python
class ConsolidationMemoryCommand(MemoryFields):
    """Validated deterministic extractor output."""

    source_detail: dict = Field(default_factory=dict)
```

Replace the `source_detail` argument in `MemoryManager.create_consolidated` with:

```python
            source_detail={
                **payload.source_detail,
                "skill_id": "memory_consolidation",
                "skill_version": skill_version,
                "extractor": "deterministic_v1",
            },
```

Keep `MemoryManager.create_manual` fixed to
`{"created_via": "memory_api"}` so callers cannot spoof provenance.

- [ ] **Step 4: Verify**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_extractor.py tests/test_memory_manager.py -v
```

Expected:

```text
All extractor and manager tests pass.
```

- [ ] **Step 5: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/memory/extractor.py backend/app/schemas/memory.py backend/app/memory/manager.py backend/tests/test_memory_extractor.py
git commit -m "feat(memory): add consolidation extractor"
```

### Task 7: Expose memory CRUD and search APIs

**Files:**
- Create: `backend/app/api/routes_memories.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_memory_api.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/test_memory_api.py`:

```python
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app


@pytest.mark.asyncio
async def test_memory_crud_search_and_soft_delete() -> None:
    project_id = uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created_response = await client.post(
            "/api/v1/memories",
            json={
                "memory_type": "project",
                "scope": "project",
                "project_id": str(project_id),
                "content": "PostgreSQL is the canonical memory store.",
                "summary": "Canonical store",
                "importance": "0.8000",
                "confidence": "0.9000",
                "tags": ["p6", "postgresql"],
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()

        listed = await client.get(
            "/api/v1/memories",
            params={"project_id": str(project_id), "tag": "p6"},
        )
        assert listed.status_code == 200
        assert listed.json()["items"][0]["memory_id"] == created["memory_id"]

        searched = await client.post(
            "/api/v1/memories/search",
            json={
                "query": "PostgreSQL canonical",
                "project_id": str(project_id),
                "limit": 5,
            },
        )
        assert searched.status_code == 200
        assert searched.json()["items"][0]["memory"]["memory_id"] == created["memory_id"]

        updated = await client.patch(
            f"/api/v1/memories/{created['memory_id']}",
            json={"version": 1, "summary": "PostgreSQL canonical record"},
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == 2

        deleted = await client.delete(
            f"/api/v1/memories/{created['memory_id']}",
            params={"version": 2},
        )
        assert deleted.status_code == 204

        missing = await client.get(
            f"/api/v1/memories/{created['memory_id']}"
        )
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_create_returns_existing_memory_id() -> None:
    settings = get_settings()
    payload = {
        "memory_type": "semantic",
        "scope": "user",
        "content": "A stable duplicate fact.",
        "importance": "0.5000",
        "confidence": "0.8000",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post("/api/v1/memories", json=payload)
        second = await client.post(
            "/api/v1/memories",
            json={**payload, "content": " A  stable duplicate fact. "},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["memory_id"] == first.json()["memory_id"]
    assert settings.default_user_id
```

- [ ] **Step 2: Confirm the route is missing**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_api.py -v
```

Expected:

```text
The requests return 404 because /api/v1/memories is not registered.
```

- [ ] **Step 3: Implement the complete router**

Create `backend/app/api/routes_memories.py`:

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repositories.memories import MemoryRepository
from app.db.session import get_session
from app.memory.manager import (
    DuplicateMemoryError,
    MemoryManager,
    MemoryNotFoundError,
    MemoryVersionConflictError,
)
from app.memory.retriever import MemoryRetriever
from app.schemas.memory import (
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryUpdate,
)

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def conflict_response(exc: Exception, memory_id: uuid.UUID) -> JSONResponse:
    body = {"detail": str(exc), "memory_id": str(memory_id)}
    if isinstance(exc, MemoryVersionConflictError):
        body["current_version"] = exc.current_version
    return JSONResponse(status_code=409, content=body)


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate,
    session: SessionDependency,
) -> MemoryRead | JSONResponse:
    try:
        memory = await MemoryManager(session).create_manual(
            user_id=get_settings().default_user_id,
            payload=payload,
        )
        return MemoryRead.model_validate(memory)
    except DuplicateMemoryError as exc:
        return conflict_response(exc, exc.memory_id)


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    session: SessionDependency,
    memory_type: str | None = None,
    scope: str | None = None,
    project_id: uuid.UUID | None = None,
    tag: str | None = None,
    include_expired: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> MemoryListResponse:
    rows, next_cursor = await MemoryRepository(session).list_owned(
        user_id=get_settings().default_user_id,
        memory_type=memory_type,
        scope=scope,
        project_id=project_id,
        tag=tag,
        include_expired=include_expired,
        limit=limit,
        cursor=cursor,
    )
    return MemoryListResponse(
        items=[MemoryRead.model_validate(row) for row in rows],
        next_cursor=next_cursor,
    )


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    payload: MemorySearchRequest,
    session: SessionDependency,
) -> MemorySearchResponse:
    hits = await MemoryRetriever(
        repository=MemoryRepository(session)
    ).search(
        user_id=get_settings().default_user_id,
        query=payload.query,
        project_id=payload.project_id,
        memory_types=payload.memory_types,
        tags=payload.tags,
        limit=payload.limit,
        touch_access=False,
    )
    return MemorySearchResponse(items=hits)


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(
    memory_id: uuid.UUID,
    session: SessionDependency,
) -> MemoryRead:
    try:
        memory = await MemoryManager(session).get(
            memory_id=memory_id,
            user_id=get_settings().default_user_id,
        )
        return MemoryRead.model_validate(memory)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc


@router.patch("/{memory_id}", response_model=MemoryRead)
async def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
    session: SessionDependency,
) -> MemoryRead | JSONResponse:
    try:
        memory = await MemoryManager(session).update(
            memory_id=memory_id,
            user_id=get_settings().default_user_id,
            payload=payload,
        )
        return MemoryRead.model_validate(memory)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    except DuplicateMemoryError as exc:
        return conflict_response(exc, exc.memory_id)
    except MemoryVersionConflictError as exc:
        return conflict_response(exc, memory_id)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: uuid.UUID,
    session: SessionDependency,
    version: Annotated[int, Query(ge=1)],
) -> Response | JSONResponse:
    try:
        await MemoryManager(session).delete(
            memory_id=memory_id,
            user_id=get_settings().default_user_id,
            version=version,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    except MemoryVersionConflictError as exc:
        return conflict_response(exc, memory_id)
```

The router deliberately declares `/search` before `/{memory_id}`.

- [ ] **Step 4: Register the router**

Apply this exact change to `backend/app/main.py`:

```diff
 from app.api.routes_health import router as health_router
+from app.api.routes_memories import router as memories_router
 from app.api.routes_skills import router as skills_router
@@
 app.include_router(agent_router)
 app.include_router(skills_router)
+app.include_router(memories_router)
```

- [ ] **Step 5: Verify**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_memory_api.py -v
uv run python -c "from app.main import app; print(sorted(path for path in app.openapi()['paths'] if 'memories' in path))"
```

Expected:

```text
All memory API tests pass.
['/api/v1/memories', '/api/v1/memories/search', '/api/v1/memories/{memory_id}']
```

- [ ] **Step 6: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/api/routes_memories.py backend/app/main.py backend/tests/test_memory_api.py
git commit -m "feat(memory): expose memory APIs"
```

### Task 8: Publish P6 Skill memory policies

**Files:**
- Modify: `backend/app/schemas/skill.py`
- Modify: `backend/app/skills/definitions/tech_qa.yaml`
- Modify: `backend/app/skills/definitions/learning_path.yaml`
- Modify: `backend/app/skills/definitions/project_summary.yaml`
- Modify: `backend/app/skills/definitions/memory_consolidation.yaml`
- Test: `backend/tests/test_skill_memory_policy.py`

- [ ] **Step 1: Write the failing policy tests**

Create `backend/tests/test_skill_memory_policy.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.skill import SkillDefinition, SkillMemoryPolicy
from app.skills.loader import load_all_skill_definitions


def test_write_requires_read() -> None:
    with pytest.raises(ValidationError, match="write requires read"):
        SkillMemoryPolicy(read=False, write=True)


def test_only_memory_consolidation_can_write() -> None:
    definitions = {
        item.definition.skill_id: item.definition
        for item in load_all_skill_definitions()
    }

    assert definitions["tech_qa"].memory_policy.model_dump() == {
        "read": True,
        "write": False,
    }
    assert definitions["learning_path"].memory_policy.read is True
    assert definitions["project_summary"].memory_policy.read is True
    assert definitions["memory_consolidation"].memory_policy.model_dump() == {
        "read": True,
        "write": True,
    }
    assert all(
        not definition.memory_policy.write
        for skill_id, definition in definitions.items()
        if skill_id != "memory_consolidation"
    )


def test_non_consolidation_definition_cannot_enable_write() -> None:
    definition = next(
        item.definition
        for item in load_all_skill_definitions()
        if item.definition.skill_id == "tech_qa"
    )
    data = definition.model_dump()
    data["memory_policy"] = {"read": True, "write": True}

    with pytest.raises(ValidationError, match="memory_consolidation"):
        SkillDefinition.model_validate(data)
```

- [ ] **Step 2: Replace the P5-only policy validator**

Replace the complete `SkillMemoryPolicy` class in `backend/app/schemas/skill.py` with:

```python
class SkillMemoryPolicy(BaseModel):
    """P6 memory permissions carried by an immutable Skill version."""

    read: bool
    write: bool

    @model_validator(mode="after")
    def write_requires_read(self) -> "SkillMemoryPolicy":
        if self.write and not self.read:
            raise ValueError("memory write requires read")
        return self
```

Add this validation to the end of `SkillDefinition._cross_field_consistency`, before `return self`:

```python
        if self.memory_policy.write and self.skill_id != "memory_consolidation":
            raise ValueError(
                "only memory_consolidation may enable memory write"
            )
```

- [ ] **Step 3: Apply the exact YAML version and policy changes**

Apply:

```diff
--- backend/app/skills/definitions/tech_qa.yaml
+++ backend/app/skills/definitions/tech_qa.yaml
@@
-version: 1.0.0
+version: 1.1.0
@@
-  read: false
+  read: true
   write: false
--- backend/app/skills/definitions/learning_path.yaml
+++ backend/app/skills/definitions/learning_path.yaml
@@
-version: 1.0.0
+version: 1.1.0
@@
-  read: false
+  read: true
   write: false
--- backend/app/skills/definitions/project_summary.yaml
+++ backend/app/skills/definitions/project_summary.yaml
@@
-version: 1.0.0
+version: 1.1.0
@@
-  read: false
+  read: true
   write: false
--- backend/app/skills/definitions/memory_consolidation.yaml
+++ backend/app/skills/definitions/memory_consolidation.yaml
@@
-version: 1.0.0
+version: 1.1.0
@@
-  read: false
-  write: false
+  read: true
+  write: true
```

No other Skill YAML changes in P6.

- [ ] **Step 4: Verify**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_skill_memory_policy.py tests/test_skill_loader.py tests/test_skill_synchronizer.py -v
```

Expected:

```text
All selected Skill tests pass, and existing 1.0.0 database versions remain immutable.
```

- [ ] **Step 5: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/schemas/skill.py backend/app/skills/definitions backend/tests/test_skill_memory_policy.py
git commit -m "feat(memory): publish skill memory policies"
```

### Task 9: Integrate memory read/write into Mock Run events

**Files:**
- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/agent/mock_runner.py`
- Test: `backend/tests/test_mock_runner_memory.py`

- [ ] **Step 1: Write the integration tests**

Create `backend/tests/test_mock_runner_memory.py`:

```python
from uuid import uuid4

import pytest

from app.agent.mock_runner import MockAgentRunner
from app.db.repositories.memories import MemoryRepository
from app.schemas.agent import RuntimeEventPayload


def test_runtime_payload_accepts_memory_summaries() -> None:
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


@pytest.mark.asyncio
async def test_memory_consolidation_writes_only_through_manager(
    db_session,
) -> None:
    runner = MockAgentRunner(event_broker=None)
    user_id = uuid4()
    run_id = uuid4()

    results = await runner._consolidate_memories(
        session=db_session,
        user_id=user_id,
        project_id=None,
        run_id=run_id,
        skill_version="1.1.0",
        text="Remember that FastAPI uses dependency injection.",
    )
    rows = await MemoryRepository(db_session).search_candidates(
        user_id=user_id,
        project_id=None,
        memory_types=[],
        tags=[],
    )

    assert len(results) == 1
    assert len(rows) == 1
    assert rows[0].source_type == "consolidation"
```

- [ ] **Step 2: Extend the event contract**

Apply this exact change to `backend/app/schemas/agent.py`:

```diff
 AgentRunEventType = Literal[
     "skill.matched",
+    "memory.retrieval.started",
+    "memory.retrieval.completed",
+    "memory.write.started",
+    "memory.write.completed",
     "run.started",
@@
 class RuntimeEventPayload(BaseModel):
@@
     skill_selection_mode: str | None = None
+    memory_query: str | None = None
+    memories: list[dict] = Field(default_factory=list)
+    memory_write_count: int | None = None
```

- [ ] **Step 3: Add complete runner helper methods**

Add these imports to `backend/app/agent/mock_runner.py`:

```python
from app.db.repositories.memories import MemoryRepository
from app.memory.extractor import MockMemoryExtractor
from app.memory.manager import MemoryManager
from app.memory.retriever import MemoryRetriever
from app.schemas.skill import SkillMemoryPolicy
```

Change the constructor signature and body to:

```python
    def __init__(
        self,
        event_broker: AgentRunEventBroker | None,
    ) -> None:
        self.event_broker = event_broker
        self._tasks: set[asyncio.Task[None]] = set()
        self.memory_extractor = MockMemoryExtractor()
```

Replace the broker notification block in `_publish_event` with:

```python
        if self.event_broker is not None:
            try:
                await self.event_broker.notify(run_id)
            except Exception:
                pass
```

Add these methods inside `MockAgentRunner`:

```python
    async def _retrieve_memories(
        self,
        *,
        session,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        query: str,
    ) -> list[dict]:
        hits = await MemoryRetriever(
            repository=MemoryRepository(session)
        ).search(
            user_id=user_id,
            query=query,
            project_id=project_id,
            memory_types=[],
            tags=[],
            limit=5,
            touch_access=True,
        )
        return [
            {
                "memory_id": str(hit.memory.memory_id),
                "memory_type": hit.memory.memory_type,
                "summary": hit.memory.summary or hit.memory.content[:120],
                "score": hit.score,
            }
            for hit in hits
        ]

    async def _consolidate_memories(
        self,
        *,
        session,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        run_id: uuid.UUID,
        skill_version: str,
        text: str,
    ) -> list[dict]:
        commands = self.memory_extractor.extract(
            text=text,
            project_id=project_id,
            run_id=run_id,
        )
        manager = MemoryManager(session)
        results = []
        for command in commands:
            result = await manager.create_consolidated(
                user_id=user_id,
                run_id=run_id,
                skill_version=skill_version,
                payload=command,
            )
            results.append(
                {
                    "memory_id": str(result.memory.memory_id),
                    "memory_type": result.memory.memory_type,
                    "summary": result.memory.summary
                    or result.memory.content[:120],
                    "created": result.created,
                    "deduplicated": result.deduplicated,
                }
            )
        return results
```

Immediately before `if skill_run is not None:`, initialize:

```python
                version_str = ""
                snapshot: dict = {}
                memory_policy = SkillMemoryPolicy(
                    read=False,
                    write=False,
                )
```

Inside `if skill_run is not None:`, after loading its `definition_snapshot`, assign:

```python
                memory_policy = SkillMemoryPolicy.model_validate(
                    snapshot.get(
                        "memory_policy",
                        {"read": False, "write": False},
                    )
                )
```

Immediately before `node.started`, add:

```python
                if memory_policy.read:
                    await self._publish_event(
                        session,
                        run_id=run_id,
                        event_type="memory.retrieval.started",
                        status="running",
                        payload=RuntimeEventPayload(memory_query=run.input),
                    )
                    memories = await self._retrieve_memories(
                        session=session,
                        user_id=run.user_id,
                        project_id=run.project_id,
                        query=run.input,
                    )
                    await self._publish_event(
                        session,
                        run_id=run_id,
                        event_type="memory.retrieval.completed",
                        status="running",
                        payload=RuntimeEventPayload(
                            memory_query=run.input,
                            memories=memories,
                        ),
                    )
```

Immediately before `run.completed`, add:

```python
                if memory_policy.write:
                    await self._publish_event(
                        session,
                        run_id=run_id,
                        event_type="memory.write.started",
                        status="running",
                        payload=RuntimeEventPayload(),
                    )
                    written = await self._consolidate_memories(
                        session=session,
                        user_id=run.user_id,
                        project_id=run.project_id,
                        run_id=run_id,
                        skill_version=version_str,
                        text=run.input,
                    )
                    await self._publish_event(
                        session,
                        run_id=run_id,
                        event_type="memory.write.completed",
                        status="running",
                        payload=RuntimeEventPayload(
                            memories=written,
                            memory_write_count=len(written),
                        ),
                    )
```

- [ ] **Step 4: Verify**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest tests/test_mock_runner_memory.py tests/test_agent_events.py tests/test_agent_api.py -v
```

Expected:

```text
All selected runtime tests pass and event sequence remains strictly increasing.
```

- [ ] **Step 5: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add backend/app/schemas/agent.py backend/app/agent/mock_runner.py backend/tests/test_mock_runner_memory.py
git commit -m "feat(memory): integrate mock runtime memory flow"
```

### Task 10: Build the frontend memory management page

**Files:**
- Create: `frontend/src/api/memories.ts`
- Create: `frontend/src/components/memory/MemoryEditor.vue`
- Create: `frontend/src/components/memory/MemoryList.vue`
- Create: `frontend/src/pages/MemoryPage.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/WorkbenchLayout.vue`

- [ ] **Step 1: Create the complete API client**

Create `frontend/src/api/memories.ts`:

```typescript
import { http } from './http'

export type MemoryType =
  | 'short_term'
  | 'learning_profile'
  | 'semantic'
  | 'episodic'
  | 'project'
  | 'procedural'
  | 'task'
  | 'runtime'

export type MemoryScope = 'user' | 'project'

export interface Memory {
  memory_id: string
  project_id: string | null
  memory_type: MemoryType
  scope: MemoryScope
  content: string
  summary: string | null
  importance: string
  confidence: string
  source_type: 'manual' | 'agent_run' | 'consolidation'
  source_id: string | null
  source_detail: Record<string, unknown>
  tags: string[]
  version: number
  access_count: number
  last_accessed_at: string | null
  expires_at: string | null
  sync_status: string
  created_at: string
  updated_at: string
}

export interface MemoryWrite {
  memory_type: MemoryType
  scope: MemoryScope
  project_id: string | null
  content: string
  summary: string | null
  importance: string
  confidence: string
  tags: string[]
}

export interface MemoryListResponse {
  items: Memory[]
  next_cursor: string | null
}

export async function listMemories(): Promise<MemoryListResponse> {
  const response = await http.get<MemoryListResponse>('/v1/memories')
  return response.data
}

export async function createMemory(payload: MemoryWrite): Promise<Memory> {
  const response = await http.post<Memory>('/v1/memories', payload)
  return response.data
}

export async function updateMemory(
  memoryId: string,
  payload: Partial<MemoryWrite> & { version: number },
): Promise<Memory> {
  const response = await http.patch<Memory>(
    `/v1/memories/${memoryId}`,
    payload,
  )
  return response.data
}

export async function deleteMemory(
  memoryId: string,
  version: number,
): Promise<void> {
  await http.delete(`/v1/memories/${memoryId}`, {
    params: { version },
  })
}
```

- [ ] **Step 2: Create the complete editor**

Create `frontend/src/components/memory/MemoryEditor.vue`:

```vue
<script setup lang="ts">
import { reactive, watch } from 'vue'
import { ElButton, ElForm, ElFormItem, ElInput, ElOption, ElSelect } from 'element-plus'

import type { Memory, MemoryScope, MemoryType, MemoryWrite } from '../../api/memories'

const props = defineProps<{ memory: Memory | null }>()
const emit = defineEmits<{
  save: [payload: MemoryWrite]
  cancel: []
}>()

const form = reactive<MemoryWrite>({
  memory_type: 'semantic',
  scope: 'user',
  project_id: null,
  content: '',
  summary: null,
  importance: '0.5000',
  confidence: '0.8000',
  tags: [],
})

watch(
  () => props.memory,
  (memory) => {
    Object.assign(
      form,
      memory
        ? {
            memory_type: memory.memory_type,
            scope: memory.scope,
            project_id: memory.project_id,
            content: memory.content,
            summary: memory.summary,
            importance: memory.importance,
            confidence: memory.confidence,
            tags: [...memory.tags],
          }
        : {
            memory_type: 'semantic',
            scope: 'user',
            project_id: null,
            content: '',
            summary: null,
            importance: '0.5000',
            confidence: '0.8000',
            tags: [],
          },
    )
  },
  { immediate: true },
)

function submit(): void {
  emit('save', {
    ...form,
    project_id: form.scope === 'project' ? form.project_id : null,
    tags: [...form.tags],
  })
}
</script>

<template>
  <ElForm label-position="top" @submit.prevent="submit">
    <div class="memory-editor-grid">
      <ElFormItem label="Type">
        <ElSelect v-model="form.memory_type">
          <ElOption
            v-for="item in ['learning_profile', 'semantic', 'episodic', 'project', 'procedural', 'task', 'runtime']"
            :key="item"
            :label="item"
            :value="item as MemoryType"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="Scope">
        <ElSelect v-model="form.scope">
          <ElOption label="user" :value="'user' as MemoryScope" />
          <ElOption label="project" :value="'project' as MemoryScope" />
        </ElSelect>
      </ElFormItem>
    </div>
    <ElFormItem v-if="form.scope === 'project'" label="Project UUID">
      <ElInput v-model="form.project_id" />
    </ElFormItem>
    <ElFormItem label="Content">
      <ElInput v-model="form.content" type="textarea" :rows="5" />
    </ElFormItem>
    <ElFormItem label="Summary">
      <ElInput v-model="form.summary" />
    </ElFormItem>
    <div class="memory-editor-grid">
      <ElFormItem label="Importance">
        <ElInput v-model="form.importance" />
      </ElFormItem>
      <ElFormItem label="Confidence">
        <ElInput v-model="form.confidence" />
      </ElFormItem>
    </div>
    <ElFormItem label="Tags">
      <ElSelect v-model="form.tags" multiple allow-create filterable />
    </ElFormItem>
    <div class="memory-editor-actions">
      <ElButton @click="emit('cancel')">Cancel</ElButton>
      <ElButton type="primary" native-type="submit">Save memory</ElButton>
    </div>
  </ElForm>
</template>
```

- [ ] **Step 3: Create the complete list**

Create `frontend/src/components/memory/MemoryList.vue`:

```vue
<script setup lang="ts">
import { ElButton, ElEmpty, ElTable, ElTableColumn, ElTag } from 'element-plus'

import type { Memory } from '../../api/memories'

defineProps<{ items: Memory[]; loading: boolean }>()
const emit = defineEmits<{
  edit: [memory: Memory]
  remove: [memory: Memory]
}>()
</script>

<template>
  <ElTable v-if="items.length" :data="items" v-loading="loading">
    <ElTableColumn prop="memory_type" label="Type" width="150">
      <template #default="{ row }">
        <ElTag effect="plain">{{ row.memory_type }}</ElTag>
      </template>
    </ElTableColumn>
    <ElTableColumn label="Memory" min-width="360">
      <template #default="{ row }">
        <strong>{{ row.summary || row.content.slice(0, 80) }}</strong>
        <p>{{ row.content }}</p>
      </template>
    </ElTableColumn>
    <ElTableColumn label="Tags" width="220">
      <template #default="{ row }">{{ row.tags.join(', ') || 'None' }}</template>
    </ElTableColumn>
    <ElTableColumn prop="access_count" label="Access" width="90" />
    <ElTableColumn label="Actions" width="160">
      <template #default="{ row }">
        <ElButton link type="primary" @click="emit('edit', row)">Edit</ElButton>
        <ElButton link type="danger" @click="emit('remove', row)">Delete</ElButton>
      </template>
    </ElTableColumn>
  </ElTable>
  <ElEmpty v-else description="No long-term memories yet." />
</template>
```

- [ ] **Step 4: Create the complete page**

Create `frontend/src/pages/MemoryPage.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElButton, ElDialog, ElMessage, ElMessageBox } from 'element-plus'

import {
  createMemory,
  deleteMemory,
  listMemories,
  updateMemory,
  type Memory,
  type MemoryWrite,
} from '../api/memories'
import MemoryEditor from '../components/memory/MemoryEditor.vue'
import MemoryList from '../components/memory/MemoryList.vue'

const items = ref<Memory[]>([])
const loading = ref(false)
const editorOpen = ref(false)
const editing = ref<Memory | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = (await listMemories()).items
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editing.value = null
  editorOpen.value = true
}

function openEdit(memory: Memory): void {
  editing.value = memory
  editorOpen.value = true
}

async function save(payload: MemoryWrite): Promise<void> {
  if (editing.value) {
    await updateMemory(editing.value.memory_id, {
      ...payload,
      version: editing.value.version,
    })
  } else {
    await createMemory(payload)
  }
  editorOpen.value = false
  ElMessage.success('Memory saved')
  await load()
}

async function remove(memory: Memory): Promise<void> {
  await ElMessageBox.confirm('Soft-delete this memory?', 'Confirm')
  await deleteMemory(memory.memory_id, memory.version)
  ElMessage.success('Memory deleted')
  await load()
}

onMounted(load)
</script>

<template>
  <section class="memory-page">
    <header class="memory-page-header">
      <div>
        <span class="eyebrow">Long-Term Memory V1</span>
        <h2>Canonical memories</h2>
        <p>PostgreSQL records with deterministic retrieval and Milvus projection status.</p>
      </div>
      <ElButton type="primary" @click="openCreate">New memory</ElButton>
    </header>
    <MemoryList
      :items="items"
      :loading="loading"
      @edit="openEdit"
      @remove="remove"
    />
    <ElDialog v-model="editorOpen" :title="editing ? 'Edit memory' : 'New memory'" width="640">
      <MemoryEditor
        :memory="editing"
        @save="save"
        @cancel="editorOpen = false"
      />
    </ElDialog>
  </section>
</template>
```

- [ ] **Step 5: Register navigation**

Apply to `frontend/src/router/index.ts`:

```diff
 import DashboardPage from '../pages/DashboardPage.vue'
+import MemoryPage from '../pages/MemoryPage.vue'
@@
         {
           path: 'chat',
@@
         },
+        {
+          path: 'memory',
+          name: 'memory',
+          component: MemoryPage,
+          meta: { title: 'Memory' },
+        },
```

Apply to `frontend/src/layouts/WorkbenchLayout.vue`:

```diff
         <RouterLink to="/dashboard">Dashboard</RouterLink>
         <RouterLink to="/chat">Chat</RouterLink>
+        <RouterLink to="/memory">Memory</RouterLink>
@@
-      <p class="phase-label">P3 / ChatPage Mock</p>
+      <p class="phase-label">P6 / Long-Term Memory V1</p>
```

- [ ] **Step 6: Verify and commit**

```powershell
Set-Location G:\桌面\ParisAgent\frontend
pnpm build
Set-Location ..
git add frontend/src/api/memories.ts frontend/src/components/memory frontend/src/pages/MemoryPage.vue frontend/src/router/index.ts frontend/src/layouts/WorkbenchLayout.vue
git commit -m "feat(memory): add memory management page"
```

Expected:

```text
vue-tsc and vite build both exit with code 0.
```

### Task 11: Show memory events in the Agent Runtime panel

**Files:**
- Modify: `frontend/src/api/agentEvents.ts`
- Modify: `frontend/src/stores/agentRun.ts`
- Modify: `frontend/src/components/chat/AgentRunPanel.vue`

- [ ] **Step 1: Extend frontend event types**

Apply to `frontend/src/api/agentEvents.ts`:

```diff
 export type AgentRunEventType =
   | 'skill.matched'
+  | 'memory.retrieval.started'
+  | 'memory.retrieval.completed'
+  | 'memory.write.started'
+  | 'memory.write.completed'
@@
 export interface RuntimeEventPayload {
@@
   skill_selection_mode?: string | null
+  memory_query?: string | null
+  memories?: Array<Record<string, unknown>>
+  memory_write_count?: number | null
@@
     const eventTypes: AgentRunEventType[] = [
       'skill.matched',
+      'memory.retrieval.started',
+      'memory.retrieval.completed',
+      'memory.write.started',
+      'memory.write.completed',
```

- [ ] **Step 2: Track memory summaries in Pinia**

Add after `skillInfo` in `frontend/src/stores/agentRun.ts`:

```typescript
  const retrievedMemories = ref<Array<Record<string, unknown>>>([])
  const writtenMemories = ref<Array<Record<string, unknown>>>([])
```

Add these switch cases before `run.started`:

```typescript
      case 'memory.retrieval.completed':
        retrievedMemories.value = envelope.payload.memories ?? []
        break

      case 'memory.write.completed':
        writtenMemories.value = envelope.payload.memories ?? []
        break
```

Add to both `submitMessage` reset section and `reset()`:

```typescript
    retrievedMemories.value = []
    writtenMemories.value = []
```

Add to the returned store object:

```typescript
    retrievedMemories,
    writtenMemories,
```

- [ ] **Step 3: Pass and render the memory summaries**

Add these props to `AgentRunPanel.vue`:

```typescript
  retrievedMemories: Array<Record<string, unknown>>
  writtenMemories: Array<Record<string, unknown>>
```

Add this block before the event timeline:

```vue
    <section v-if="retrievedMemories.length || writtenMemories.length" class="runtime-memory">
      <h3>Memories</h3>
      <p>Retrieved: {{ retrievedMemories.length }}</p>
      <ul>
        <li v-for="item in retrievedMemories" :key="String(item.memory_id)">
          {{ item.memory_type }} · {{ item.summary }}
        </li>
      </ul>
      <p>Written: {{ writtenMemories.length }}</p>
      <ul>
        <li v-for="item in writtenMemories" :key="String(item.memory_id)">
          {{ item.memory_type }} · {{ item.summary }}
        </li>
      </ul>
    </section>
```

In `frontend/src/pages/ChatPage.vue`, add these bindings to `AgentRunPanel`:

```vue
      :retrieved-memories="store.retrievedMemories"
      :written-memories="store.writtenMemories"
```

- [ ] **Step 4: Verify and commit**

```powershell
Set-Location G:\桌面\ParisAgent\frontend
pnpm build
Set-Location ..
git add frontend/src/api/agentEvents.ts frontend/src/stores/agentRun.ts frontend/src/components/chat/AgentRunPanel.vue frontend/src/pages/ChatPage.vue
git commit -m "feat(memory): visualize runtime memory events"
```

Expected:

```text
The frontend build exits with code 0.
```

### Task 12: Run the P6 acceptance suite and document the boundary

**Files:**
- Modify: `docs/FULLSTACK_TECH_DESIGN.md`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`

- [ ] **Step 1: Add the exact P6 boundary to documentation**

Append this section to `docs/FULLSTACK_TECH_DESIGN.md`:

```markdown
## P6 Long-Term Memory V1

P6 stores canonical long-term memories in PostgreSQL and exposes user-scoped CRUD, exact deduplication, optimistic locking, deterministic retrieval, controlled Skill memory policies, Runtime Events, and the `/memory` workbench page.

Milvus is not connected in P6. Every memory remains `sync_status=not_indexed`; the Milvus projection worker and vector search begin in P7. P6 also does not use an LLM extractor, RabbitMQ, Elasticsearch, or Neo4j.
```

Append to `backend/README.md`:

```markdown
### Memory API

Run `uv run alembic upgrade head`, then use `/api/v1/memories` for CRUD and `/api/v1/memories/search` for deterministic PostgreSQL retrieval.
```

Append to `frontend/README.md`:

```markdown
### Memory page

Open `/memory` to create, edit, inspect, and soft-delete P6 long-term memories. The Chat Runtime panel shows memory retrieval and consolidation events emitted by policy-enabled Skills.
```

- [ ] **Step 2: Apply the migration against the development database**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run alembic upgrade head
uv run alembic current
```

Expected:

```text
The current revision is 20260614_0004.
```

- [ ] **Step 3: Run the complete backend and frontend verification**

```powershell
Set-Location G:\桌面\ParisAgent\backend
uv run pytest
Set-Location ..\frontend
pnpm build
```

Expected:

```text
All backend tests pass.
The frontend build exits with code 0.
```

- [ ] **Step 4: Scan for prohibited incomplete output**

```powershell
Set-Location G:\桌面\ParisAgent
rg -n "TBD|TODO|implementation omitted|similar to above|rest unchanged" backend/app backend/tests frontend/src
```

Expected:

```text
No matches in P6 implementation files or this plan.
```

- [ ] **Step 5: Perform the manual acceptance flow**

```text
1. Start PostgreSQL, Redis, and RabbitMQ with the existing Docker Compose configuration.
2. Start the backend with: uv run uvicorn app.main:app --reload
3. Start the frontend with: pnpm dev
4. Open /memory and create a semantic user memory.
5. Edit it and confirm the version increments.
6. Run tech_qa from /chat and confirm memory.retrieval.started/completed appear.
7. Run memory_consolidation with “Remember that Paris Agent uses Milvus in P7.”
8. Confirm memory.write.started/completed appear and the new memory is visible on /memory.
9. Repeat the same consolidation input and confirm no duplicate active row is created.
10. Confirm every row has sync_status=not_indexed.
```

- [ ] **Step 6: Commit**

```powershell
Set-Location G:\桌面\ParisAgent
git add docs/FULLSTACK_TECH_DESIGN.md backend/README.md frontend/README.md
git commit -m "docs(memory): document P6 acceptance boundary"
git status --short
```

Expected:

```text
The P6 branch is clean after all task commits.
```

## Plan Review Checklist

- [ ] Every requirement in `docs/superpowers/specs/2026-06-14-p6-long-term-memory-v1-design.md` maps to a task above.
- [ ] PostgreSQL remains canonical and Milvus remains deferred to P7.
- [ ] All reads and writes are scoped by `default_user_id`.
- [ ] All writes pass through `MemoryManager`.
- [ ] Exact deduplication, soft delete, and optimistic locking are covered by tests.
- [ ] Only `memory_consolidation@1.1.0` enables memory writes.
- [ ] Runtime Events cover retrieval and writing without changing terminal event semantics.
- [ ] `/memory` supports create, list, edit, and soft delete.
- [ ] Backend tests, frontend build, migration upgrade, and manual acceptance all pass.
- [ ] The incomplete-marker scan returns no matches.
