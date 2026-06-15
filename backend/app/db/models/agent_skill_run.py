"""Agent Skill Run 执行记录表 —— Skill Registry P5。

每条记录将一次 Agent Run 与一个具体的 Skill Version 关联起来，
记录"这次 Run 使用了哪个 Skill 的哪个版本"以及该版本的定义快照。

selection_mode 区分 Skill 是显式指定还是由 Router 自动选择默认版本：
  - 'explicit' : API 调用方明确指定了 skill_id + version
  - 'default'  : Skill Router 根据 agent_skills.default_version_id 自动选择

agent_skill_runs.skill_version_id → agent_skill_versions.id  (ON DELETE RESTRICT)
    删除版本前必须先清理关联的 Run 记录，防止执行历史引用失效。
agent_skill_runs.run_id → agent_runs.run_id  (ON DELETE CASCADE)
    删除 Run 时自动清理对应的 Skill Run 记录，因为它们只是 Run 的附属信息。
"""

# ---------- 标准库 ----------
import uuid                          # 生成 UUID 业务标识（skill_run_id, run_id 引用）
from datetime import datetime        # 时间戳类型标注

# ---------- SQLAlchemy 核心类型 ----------
from sqlalchemy import (
    BigInteger,       # BIGINT：内部自增主键、外键引用
    CheckConstraint,  # CHECK 约束：在数据库层面兜底校验字段取值
    DateTime,         # TIMESTAMP 类型，配合 timezone=True 使用带时区时间
    ForeignKey,       # 外键约束：关联 agent_runs.run_id 和 agent_skill_versions.id
    Identity,         # GENERATED ALWAYS AS IDENTITY：PostgreSQL 推荐的自增主键写法
    Index,            # 显式声明索引
    Integer,          # INTEGER：SQLite 测试时 BigInteger 退化为 Integer 才能自增
    Text,             # TEXT：优先使用 TEXT 而非 VARCHAR(n)，遵循项目数据库规范
    Uuid,             # UUID 类型：PostgreSQL 原生 uuid，SQLite 测试时自动降级为 CHAR
    func,             # SQL 函数引用，这里用于 func.now() 获取数据库当前时间
    text,             # 原始 SQL 片段，用于 Index 表达式
)
# ---------- PostgreSQL 专用类型 ----------
from sqlalchemy.dialects.postgresql import JSONB  # JSONB：PostgreSQL 高性能二进制 JSON
# ---------- SQLAlchemy 可移植 JSON ----------
from sqlalchemy.types import JSON                  # JSON：SQLite 测试时使用可移植类型
# ---------- SQLAlchemy ORM 映射 ----------
from sqlalchemy.orm import Mapped, mapped_column  # 类型安全的列声明方式

from app.db.base import Base  # 声明式基类，所有 Model 都要继承它


# selection_mode 合法值常量元组，供代码中做 "if mode in SELECTION_MODES" 校验。
# 数据库层面由 CHECK 约束兜底，这里给应用层代码也提供一份单一事实来源。
SELECTION_MODES = (
    "explicit",   # API 调用方显式指定了 Skill 版本
    "default",    # Skill Router 根据 default_version_id 自动选择
)


class AgentSkillRun(Base):
    """一次 Agent Run 与 Skill Version 的关联记录。

    记录"这次 Run 用了哪个 Skill 的哪个版本"，并保存该版本的定义快照。
    即使后续 Skill 版本被更新，Run 的历史记录仍保留当时的定义快照，
    保证执行历史的可追溯性和可复现性。
    """

    __tablename__ = "agent_skill_runs"
    __table_args__ = (
        # ===== CHECK 约束：数据库层面的最后一道防线 =====

        # selection_mode 必须属于预定义的合法值集合
        CheckConstraint(
            "selection_mode IN ('explicit', 'default')",
            name="ck_agent_skill_runs_selection_mode",
        ),
        # 注：definition_snapshot 必须为 JSON 对象（非数组、非标量），
        # 但该约束无法跨 PostgreSQL / SQLite 统一实现，仅在 Python 层校验。

        # ===== 索引：加速高频查询 =====

        # 按 Skill Version 查关联的 Run 列表（"使用某版本的所有 Run"查询）
        Index(
            "ix_agent_skill_runs_version_created",
            "skill_version_id",
            text("created_at DESC"),
        ),
    )

    # ===== 内部自增主键 =====
    # PostgreSQL 用 BIGINT IDENTITY，SQLite 测试时退化为 INTEGER。
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )

    # Skill Run 全局唯一标识：UUID，对外暴露，用于 API 查询和日志关联。
    # 由 uuid.uuid4 自动生成，UNIQUE 约束防止碰撞。
    skill_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )

    # 所属 Agent Run：外键关联 agent_runs.run_id（注意不是 agent_runs.id），
    # ON DELETE CASCADE —— 删除 Run 时自动清理对应的 Skill Run 记录。
    # UNIQUE 约束保证一次 Run 最多只关联一条 Skill Run 记录（1:1 关系）。
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # 使用的 Skill 版本：外键关联 agent_skill_versions.id，
    # ON DELETE RESTRICT —— 删除版本前必须先清理关联的 Run 记录。
    skill_version_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("agent_skill_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Skill 选择模式：'explicit'（显式指定）或 'default'（Router 自动选择）。
    # 取值受上方 CHECK 约束保护。
    selection_mode: Mapped[str] = mapped_column(Text, nullable=False)

    # 执行时该 Skill 版本的定义快照（JSON 对象）：
    # 保存当时的完整定义，保证即使后续版本更新，历史 Run 仍可回溯和复现。
    # SQLite 测试使用 SQLAlchemy 可移植 JSON 类型，PostgreSQL 映射为 JSONB。
    definition_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )

    # 记录创建时间：由数据库 server_default=now() 在 INSERT 时自动生成。
    # Skill Run 记录创建后不应修改，因此没有 updated_at 字段。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
