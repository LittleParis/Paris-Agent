"""create skill registry tables

Revision ID: 20260614_0003
Revises: 20260614_0002
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260614_0003"
down_revision: str | None = "20260614_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Table 1: agent_skills ──────────────────────────────────────────
    op.create_table(
        "agent_skills",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("skill_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("default_version_id", sa.BigInteger(), nullable=True),
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
            "length(trim(name)) > 0",
            name="ck_agent_skills_name_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_agent_skills_description_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", name="uq_agent_skills_skill_id"),
    )

    # ── Table 2: agent_skill_versions ──────────────────────────────────
    op.create_table(
        "agent_skill_versions",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("agent_skill_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column(
            "definition_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(version)) > 0",
            name="ck_agent_skill_versions_version_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(content_hash)) > 0",
            name="ck_agent_skill_versions_content_hash_not_blank",
        ),
        sa.UniqueConstraint(
            "agent_skill_id",
            "version",
            name="uq_agent_skill_versions_skill_version",
        ),
        sa.ForeignKeyConstraint(
            ["agent_skill_id"],
            ["agent_skills.id"],
            ondelete="RESTRICT",
            name="fk_agent_skill_versions_agent_skill_id",
        ),
        sa.UniqueConstraint(
            "version_id",
            name="uq_agent_skill_versions_version_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_skill_versions_skill_published",
        "agent_skill_versions",
        ["agent_skill_id", sa.literal_column("published_at DESC")],
    )

    # ── Table 3: agent_skill_runs ──────────────────────────────────────
    op.create_table(
        "agent_skill_runs",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column(
            "skill_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("skill_version_id", sa.BigInteger(), nullable=False),
        sa.Column("selection_mode", sa.Text(), nullable=False),
        sa.Column(
            "definition_snapshot",
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
        sa.CheckConstraint(
            "selection_mode IN ('explicit', 'default')",
            name="ck_agent_skill_runs_selection_mode",
        ),
        sa.UniqueConstraint(
            "skill_run_id",
            name="uq_agent_skill_runs_skill_run_id",
        ),
        sa.UniqueConstraint(
            "run_id",
            name="uq_agent_skill_runs_run_id",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.run_id"],
            ondelete="CASCADE",
            name="fk_agent_skill_runs_run_id",
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["agent_skill_versions.id"],
            ondelete="RESTRICT",
            name="fk_agent_skill_runs_skill_version_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_skill_runs_version_created",
        "agent_skill_runs",
        ["skill_version_id", sa.literal_column("created_at DESC")],
    )

    # ── Circular FK: agent_skills.default_version_id → agent_skill_versions.id
    op.create_foreign_key(
        "fk_agent_skills_default_version_id",
        "agent_skills",
        "agent_skill_versions",
        ["default_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 1. Drop the circular FK first
    op.drop_constraint(
        "fk_agent_skills_default_version_id",
        "agent_skills",
        type_="foreignkey",
    )

    # 2. Drop agent_skill_runs (with its index)
    op.drop_index(
        "ix_agent_skill_runs_version_created",
        table_name="agent_skill_runs",
    )
    op.drop_table("agent_skill_runs")

    # 3. Drop agent_skill_versions (with its index)
    op.drop_index(
        "ix_agent_skill_versions_skill_published",
        table_name="agent_skill_versions",
    )
    op.drop_table("agent_skill_versions")

    # 4. Drop agent_skills
    op.drop_table("agent_skills")
