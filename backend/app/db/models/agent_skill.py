"""Agent Skill 注册表 —— Skill Registry P5。

每条记录代表一个已注册的 Skill（如 "tech_qa"、"learning_path"）。
Skill 本身只保存元信息和启用状态；具体执行逻辑的版本快照存储在
agent_skill_versions 表中，通过 default_version_id 指向当前生效版本。

default_version_id 的 FK 不在 ORM 层声明，而是通过后续 Alembic Migration
手动添加，以避免 agent_skills ↔ agent_skill_versions 之间的循环依赖。
"""

# ---------- 标准库 ----------
import re                           # Python 层正则校验 skill_id 格式
from datetime import datetime      # 时间戳类型标注

# ---------- SQLAlchemy 核心类型 ----------
from sqlalchemy import (
    BigInteger,       # BIGINT：内部自增主键
    Boolean,          # BOOLEAN：启用/禁用标记
    CheckConstraint,  # CHECK 约束：在数据库层面兜底校验字段取值
    DateTime,         # TIMESTAMP 类型，配合 timezone=True 使用带时区时间
    Identity,         # GENERATED ALWAYS AS IDENTITY：PostgreSQL 推荐的自增主键写法
    Integer,          # INTEGER：SQLite 测试时 BigInteger 退化为 Integer 才能自增
    Text,             # TEXT：优先使用 TEXT 而非 VARCHAR(n)，遵循项目数据库规范
    func,             # SQL 函数引用，这里用于 func.now() 获取数据库当前时间
)
# ---------- SQLAlchemy ORM 映射 ----------
from sqlalchemy.orm import Mapped, mapped_column  # 类型安全的列声明方式

from app.db.base import Base  # 声明式基类，所有 Model 都要继承它


# skill_id 格式正则：小写字母开头，后跟 1-127 位小写字母、数字或下划线。
# 数据库层面不做正则 CHECK（SQLite 不支持 ~ 运算符），仅在 Python 层校验。
SKILL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,127}$")


def validate_skill_id(value: str) -> str:
    """校验 skill_id 是否符合 `^[a-z][a-z0-9_]{1,127}$` 格式。

    供 Service / Pydantic Validator 调用，不符合时抛出 ValueError。
    返回原始值以便链式调用。
    """
    if not SKILL_ID_PATTERN.match(value):
        raise ValueError(
            f"skill_id 格式非法: '{value}'。"
            "必须以小写字母开头，后跟 1-127 位小写字母、数字或下划线。"
        )
    return value


class AgentSkill(Base):
    """已注册 Skill 的元信息（Skill Registry）。

    一个 Skill 对应一种 Agent 可执行的能力（如"技术问答"、"学习路径生成"）。
    Skill 本身不包含执行逻辑，执行逻辑的版本快照存储在 agent_skill_versions 表中。
    default_version_id 指向当前生效的默认版本，为空表示该 Skill 尚无可用版本。
    """

    __tablename__ = "agent_skills"
    __table_args__ = (
        # ===== CHECK 约束：数据库层面的最后一道防线 =====
        # 即使 Pydantic 校验被绕过，数据库也会拒绝非法值。
        # 注：skill_id 的正则校验无法跨 PostgreSQL/SQLite 统一实现，
        # 因此只在 Python 层（validate_skill_id）做校验。

        # name 不能为空白字符串（trim 后长度必须 > 0）
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_agent_skills_name_not_blank",
        ),
        # description 不能为空白字符串
        CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_agent_skills_description_not_blank",
        ),
    )

    # ===== 内部自增主键 =====
    # PostgreSQL 用 BIGINT IDENTITY（比 BIGSERIAL 更规范），
    # SQLite 测试时退化为 INTEGER 才能正常自增。
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )

    # Skill 业务标识：人类可读的 slug（如 "tech_qa"、"learning_path"）。
    # UNIQUE 约束防止重复注册；格式由 Python 层 validate_skill_id() 校验。
    # 不使用 UUID 是因为 skill_id 需要出现在配置文件和 API 路径中，可读性更重要。
    skill_id: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
    )

    # Skill 显示名称：用于管理后台和日志，NOT NULL 且受 CHECK 约束不能为空白。
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Skill 描述：简述该 Skill 的能力范围，NOT NULL 且受 CHECK 约束不能为空白。
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # 启用标记：False 时 Skill Router 会跳过该 Skill，相当于软禁用。
    # default / server_default 都为 True，新注册的 Skill 默认启用。
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,           # Python 层默认值（ORM 构造对象时）
        server_default="true",  # 数据库层默认值（直接 INSERT SQL 时）
    )

    # 当前生效版本的 ID：指向 agent_skill_versions.id。
    # FK 约束不在 ORM 层声明（避免 agent_skills ↔ agent_skill_versions 循环依赖），
    # 而是通过 Alembic Migration 手动 ALTER TABLE ADD CONSTRAINT 添加。
    # NULL 表示该 Skill 尚无已发布的版本。
    default_version_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
    )

    # 创建时间：由数据库 server_default=now() 在 INSERT 时自动生成，Python 代码不手动赋值。
    # timezone=True 表示存储为带时区的 TIMESTAMPTZ，避免时区歧义。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 最后更新时间：INSERT 时由 server_default=now() 初始化，
    # 每次 UPDATE 时由 SQLAlchemy 的 onupdate=func.now() 自动刷新为当前时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
