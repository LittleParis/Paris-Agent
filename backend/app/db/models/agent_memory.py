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
    UniqueConstraint,
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
            "length(btrim(content)) > 0",
            name="ck_agent_memories_content_not_blank",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_agent_memories_content_not_blank",
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            "summary IS NULL OR length(btrim(summary)) > 0",
            name="ck_agent_memories_summary_not_blank",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "summary IS NULL OR length(trim(summary)) > 0",
            name="ck_agent_memories_summary_not_blank",
        ).ddl_if(dialect="sqlite"),
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
            "jsonb_typeof(source_detail) = 'object'",
            name="ck_agent_memories_source_detail_object",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "jsonb_typeof(tags) = 'array'",
            name="ck_agent_memories_tags_array",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_agent_memories_content_hash",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_agent_memories_content_hash",
        ).ddl_if(dialect="sqlite"),
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
        UniqueConstraint(
            "memory_id",
            name="uq_agent_memories_memory_id",
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
        Index(
            "uq_agent_memories_active_content",
            "user_id",
            "scope",
            text(
                "coalesce(project_id, "
                "'00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            "memory_type",
            "content_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ).ddl_if(dialect="postgresql"),
        Index(
            "uq_agent_memories_active_content_sqlite",
            "user_id",
            "scope",
            text(
                "coalesce(project_id, "
                "'00000000-0000-0000-0000-000000000000')"
            ),
            "memory_type",
            "content_hash",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ).ddl_if(dialect="sqlite"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
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
        server_default=text("'{}'"),
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
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
