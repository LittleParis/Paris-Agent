"""Runtime Event 持久化记录。

每条 SSE 事件在发送前先写入该表，确保服务重启或断线后仍可回放。
事件序号（sequence）在同一 Run 内从 1 单调递增，由数据库唯一约束兜底。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RuntimeEvent(Base):
    """一次 Agent Run 的持久化事件记录。

    事件先写入数据库，再通过进程内 Broker 唤醒 SSE 消费者。
    该表是事件的唯一事实存储，Broker 内存中不保留历史事件。
    """

    __tablename__ = "runtime_events"
    __table_args__ = (
        # sequence 必须为正整数（从 1 开始）
        CheckConstraint(
            "sequence > 0",
            name="ck_runtime_events_sequence_positive",
        ),
        # event_type 不能为空白字符串
        CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_runtime_events_event_type_not_blank",
        ),
        # status 必须属于 Agent Run 合法状态集合
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled', 'waiting_approval')",
            name="ck_runtime_events_status",
        ),
        # 同一 Run 内的序号不能重复，也提供自然查询索引
        UniqueConstraint(
            "run_id", "sequence",
            name="uq_runtime_events_run_sequence",
        ),
        # 按 run_id + 时间排序查询
        Index(
            "ix_runtime_events_run_created",
            "run_id",
            text("created_at ASC"),
        ),
    )

    # ===== 双键策略 =====
    # id   → 数据库内部自增主键，只用于内部排序
    # event_id → UUID 事件标识，对外暴露，作为 SSE id 和去重标识

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )

    # 事件全局唯一标识，作为 SSE id 和全局去重标识
    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )

    # 所属 Agent Run，外键关联 agent_runs.run_id，级联删除
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )

    # 同一 Run 内从 1 单调递增的序号
    sequence: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        nullable=False,
    )

    # 事件类型：run.started, node.started, message.delta 等
    event_type: Mapped[str] = mapped_column(Text, nullable=False)

    # 事件产生时的 Run 状态
    status: Mapped[str] = mapped_column(Text, nullable=False)

    # 事件特有数据，始终为 JSON 对象。
    # SQLite 测试使用 SQLAlchemy 可移植 JSON 类型，PostgreSQL 映射为 JSONB。
    # Python 层 default=dict 保证 ORM 创建时始终有空对象；
    # PostgreSQL server_default 由 Migration 明确设置。
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    # 记录创建时间，由数据库 server_default=now() 生成
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
