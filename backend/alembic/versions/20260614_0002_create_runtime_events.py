"""create runtime_events table

Revision ID: 20260614_0002
Revises: 20260613_0001
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260614_0002"
down_revision: str | None = "20260613_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 序号必须为正
        sa.CheckConstraint(
            "sequence > 0",
            name="ck_runtime_events_sequence_positive",
        ),
        # 事件类型不能为空白
        sa.CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_runtime_events_event_type_not_blank",
        ),
        # 状态必须属于 Agent Run 合法状态集合
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled', 'waiting_approval')",
            name="ck_runtime_events_status",
        ),
        # 同一 Run 内序号唯一
        sa.UniqueConstraint(
            "run_id", "sequence",
            name="uq_runtime_events_run_sequence",
        ),
        # 外键关联 agent_runs，级联删除
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.run_id"],
            ondelete="CASCADE",
            name="fk_runtime_events_run_id",
        ),
        # event_id 全局唯一
        sa.UniqueConstraint("event_id", name="uq_runtime_events_event_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    # 按 run_id + 时间排序的索引
    op.create_index(
        "ix_runtime_events_run_created",
        "runtime_events",
        ["run_id", sa.literal_column("created_at ASC")],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_events_run_created", table_name="runtime_events")
    op.drop_table("runtime_events")
