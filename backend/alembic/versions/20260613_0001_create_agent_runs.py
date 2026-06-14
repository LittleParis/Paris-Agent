"""create agent_runs table

Revision ID: 20260613_0001
Revises:
Create Date: 2026-06-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260613_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # P1 仅创建 Run 主表；节点、步骤、工具与持久化事件留到对应阶段独立迁移。
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("skill_id", sa.Text(), nullable=True),
        sa.Column(
            "task_type",
            sa.Text(),
            server_default=sa.text("'chat'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("current_node", sa.Text(), nullable=True),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("final_output", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "total_tokens",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_cost",
            sa.Numeric(precision=18, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
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
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled', 'waiting_approval')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "length(btrim(input)) > 0",
            name="ck_agent_runs_input_not_blank",
        ),
        sa.CheckConstraint(
            "total_tokens >= 0",
            name="ck_agent_runs_total_tokens",
        ),
        sa.CheckConstraint(
            "total_cost >= 0",
            name="ck_agent_runs_total_cost",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_agent_runs_run_id"),
    )
    op.create_index(
        "ix_agent_runs_user_created",
        "agent_runs",
        ["user_id", sa.literal_column("created_at DESC")],
    )
    op.create_index(
        "ix_agent_runs_thread_created",
        "agent_runs",
        ["thread_id", sa.literal_column("created_at DESC")],
        postgresql_where=sa.text("thread_id IS NOT NULL"),
    )
    op.create_index(
        "ix_agent_runs_project_created",
        "agent_runs",
        ["project_id", sa.literal_column("created_at DESC")],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "ix_agent_runs_status_created",
        "agent_runs",
        ["status", "created_at"],
        # 只索引仍需调度或人工处理的活跃状态。
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'waiting_approval')"
        ),
    )


def downgrade() -> None:
    # 先删除依赖表的索引，再删除表，确保 downgrade 可逆且顺序清晰。
    op.drop_index("ix_agent_runs_status_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_project_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_thread_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_created", table_name="agent_runs")
    op.drop_table("agent_runs")
