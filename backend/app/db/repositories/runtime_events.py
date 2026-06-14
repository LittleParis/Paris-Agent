"""Runtime Event 数据访问层。

负责事件的持久化写入、序号分配和查询回放。
路由和 Runner 不直接拼接 SQL 操作 runtime_events 表。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_run import AgentRun
from app.db.models.runtime_event import RuntimeEvent
from app.schemas.agent import (
    AgentRunEventType,
    AgentRunStatus,
    RuntimeEventEnvelope,
    RuntimeEventPayload,
)


class RuntimeEventRepository:
    """封装 runtime_events 表的读写操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        run_id: uuid.UUID,
        event_type: AgentRunEventType,
        status: AgentRunStatus,
        payload: RuntimeEventPayload | None = None,
    ) -> RuntimeEvent:
        """创建并提交单条事件。

        在事务内锁定所属 agent_runs 行，查询当前最大 sequence 并加一。
        该锁将同一 Run 的并发发布串行化，不同 Run 之间互不阻塞。

        调用者必须在 commit 后再调用 Broker.notify(run_id)。
        """

        # PostgreSQL: SELECT ... FOR UPDATE 锁定 agent_runs 行
        # SQLite: 不支持行级锁，但测试仅使用单进程顺序发布；
        #         数据库唯一约束仍负责拒绝重复序号。
        stmt = select(AgentRun).where(AgentRun.run_id == run_id)
        if self.session.bind is not None and self.session.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            raise ValueError(f"Agent run {run_id} not found")

        # 查询当前最大 sequence
        seq_result = await self.session.execute(
            select(func.coalesce(func.max(RuntimeEvent.sequence), 0))
            .where(RuntimeEvent.run_id == run_id)
        )
        last_sequence = seq_result.scalar_one()
        next_sequence = last_sequence + 1

        event = RuntimeEvent(
            event_id=uuid.uuid4(),
            run_id=run_id,
            sequence=next_sequence,
            event_type=event_type,
            status=status,
            payload=(payload.model_dump(exclude_none=True)
                     if payload is not None else {}),
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def list_after_sequence(
        self,
        run_id: uuid.UUID,
        sequence: int,
    ) -> list[RuntimeEvent]:
        """按升序查询指定 sequence 之后的所有事件。"""

        result = await self.session.execute(
            select(RuntimeEvent)
            .where(
                RuntimeEvent.run_id == run_id,
                RuntimeEvent.sequence > sequence,
            )
            .order_by(RuntimeEvent.sequence.asc())
        )
        return list(result.scalars().all())

    async def get_by_event_id(self, event_id: uuid.UUID) -> RuntimeEvent | None:
        """通过事件 UUID 查找事件，用于 Last-Event-ID 游标定位。"""

        result = await self.session.execute(
            select(RuntimeEvent).where(RuntimeEvent.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_last_sequence(self, run_id: uuid.UUID) -> int:
        """获取指定 Run 的最后事件序号，辅助测试和诊断。"""

        result = await self.session.execute(
            select(func.coalesce(func.max(RuntimeEvent.sequence), 0))
            .where(RuntimeEvent.run_id == run_id)
        )
        return result.scalar_one()

    @staticmethod
    def to_envelope(event: RuntimeEvent) -> RuntimeEventEnvelope:
        """将数据库记录转换为稳定事件信封。"""

        payload_data = event.payload if isinstance(event.payload, dict) else {}
        return RuntimeEventEnvelope(
            event_id=event.event_id,
            event_type=event.event_type,
            run_id=event.run_id,
            sequence=event.sequence,
            timestamp=event.created_at,
            status=event.status,
            payload=RuntimeEventPayload(**payload_data),
        )
