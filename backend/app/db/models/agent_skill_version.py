"""Agent Skill Version 版本快照表 —— Skill Registry P5。

每条记录代表某个 Skill 的一个已发布版本。版本一旦发布即不可变（immutable），
definition_snapshot 保存该版本完整的 Skill 定义 JSON（含 prompt 模板、参数 schema、
工具编排等），content_hash 用于快速比对两个版本的内容是否一致。

agent_skill_versions.agent_skill_id → agent_skills.id  (ON DELETE RESTRICT)
    删除 Skill 前必须先删除或归档其所有版本，防止意外丢失版本历史。
"""

# ---------- 标准库 ----------
import uuid                          # 生成 UUID 业务标识（version_id）
from datetime import datetime        # 时间戳类型标注

# ---------- SQLAlchemy 核心类型 ----------
from sqlalchemy import (
    BigInteger,       # BIGINT：内部自增主键、外键引用
    CheckConstraint,  # CHECK 约束：在数据库层面兜底校验字段取值
    DateTime,         # TIMESTAMP 类型，配合 timezone=True 使用带时区时间
    ForeignKey,       # 外键约束：关联 agent_skills.id
    Identity,         # GENERATED ALWAYS AS IDENTITY：PostgreSQL 推荐的自增主键写法
    Index,            # 显式声明索引
    Integer,          # INTEGER：SQLite 测试时 BigInteger 退化为 Integer 才能自增
    Text,             # TEXT：优先使用 TEXT 而非 VARCHAR(n)，遵循项目数据库规范
    UniqueConstraint, # 复合唯一约束：(agent_skill_id, version)
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


class AgentSkillVersion(Base):
    """某个 Skill 的一个已发布版本（不可变快照）。

    版本发布后 definition_snapshot 不应再修改；如需更新 Skill 定义，
    应发布新版本。agent_skills.default_version_id 指向当前生效的版本。
    """

    __tablename__ = "agent_skill_versions"
    __table_args__ = (
        # ===== CHECK 约束：数据库层面的最后一道防线 =====

        # version 不能为空白字符串（trim 后长度必须 > 0）
        CheckConstraint(
            "length(trim(version)) > 0",
            name="ck_agent_skill_versions_version_not_blank",
        ),
        # content_hash 不能为空白字符串（trim 后长度必须 > 0）
        CheckConstraint(
            "length(trim(content_hash)) > 0",
            name="ck_agent_skill_versions_content_hash_not_blank",
        ),

        # ===== 复合唯一约束 =====
        # 同一个 Skill 下不允许发布相同版本号的两个版本
        UniqueConstraint(
            "agent_skill_id", "version",
            name="uq_agent_skill_versions_skill_version",
        ),

        # ===== 索引：加速高频查询 =====

        # 按 Skill 查版本列表（"某 Skill 的版本历史"页面，按发布时间倒序）
        Index(
            "ix_agent_skill_versions_skill_published",
            "agent_skill_id",
            text("published_at DESC"),
        ),
    )

    # ===== 内部自增主键 =====
    # PostgreSQL 用 BIGINT IDENTITY，SQLite 测试时退化为 INTEGER。
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )

    # 版本全局唯一标识：UUID，对外暴露，API 路径中通过它定位特定版本。
    # 由 uuid.uuid4 自动生成，UNIQUE 约束防止碰撞。
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )

    # 所属 Skill：外键关联 agent_skills.id，ON DELETE RESTRICT 防止误删 Skill
    # 时连带丢失所有版本历史。必须先删除/归档版本，才能删除 Skill 本身。
    agent_skill_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("agent_skills.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 语义化版本号（如 "1.0.0"、"2.1.3-beta"），同一 Skill 下唯一。
    # 唯一性由上方 UniqueConstraint (agent_skill_id, version) 保证。
    version: Mapped[str] = mapped_column(Text, nullable=False)

    # Skill 定义的完整 JSON 快照：包含 prompt 模板、参数 schema、工具编排等。
    # 版本一旦发布，此字段不应再修改（immutable snapshot）。
    # SQLite 测试使用 SQLAlchemy 可移植 JSON 类型，PostgreSQL 映射为 JSONB。
    definition_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )

    # 定义内容的哈希值（如 SHA-256），用于快速比对两个版本内容是否一致，
    # 也可用于检测定义文件是否被篡改。NOT NULL 且受 CHECK 约束不能为空白。
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # 定义文件的源路径（如 "skills/tech_qa/v1.0.0/definition.yaml"），
    # 方便开发者从版本记录回溯到源文件。NOT NULL。
    source_path: Mapped[str] = mapped_column(Text, nullable=False)

    # 版本发布时间：由数据库 server_default=now() 在 INSERT 时自动生成。
    # 版本不可变，因此没有 updated_at 字段。
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
