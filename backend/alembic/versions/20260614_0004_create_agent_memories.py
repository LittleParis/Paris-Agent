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
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
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
