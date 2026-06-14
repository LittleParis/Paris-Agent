"""P4 进程内 SSE 事件通知 Broker。

该实现只持有每个 Run 的 asyncio.Condition，用于减少同一实例内 SSE 对数据库的轮询。
不保存事件历史，也不负责分配序号。事件事实存储在 PostgreSQL runtime_events 表中。
"""

import asyncio
import uuid


class AgentRunEventBroker:
    """按 run_id 管理 asyncio.Condition，仅用于唤醒等待中的 SSE 消费者。"""

    def __init__(self) -> None:
        self._conditions: dict[uuid.UUID, asyncio.Condition] = {}

    def _condition_for(self, run_id: uuid.UUID) -> asyncio.Condition:
        """每个 Run 使用独立 Condition，避免无关 Run 互相唤醒。"""

        return self._conditions.setdefault(run_id, asyncio.Condition())

    async def notify(self, run_id: uuid.UUID) -> None:
        """通知等待中的 SSE 消费者：数据库可能有新事件。"""

        condition = self._condition_for(run_id)
        async with condition:
            condition.notify_all()

    async def wait_for_notification(
        self,
        run_id: uuid.UUID,
        timeout: float,
    ) -> bool:
        """等待通知或超时。返回 True 表示收到通知，False 表示超时。"""

        condition = self._condition_for(run_id)
        async with condition:
            try:
                await asyncio.wait_for(condition.wait(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                return False

    def clear(self) -> None:
        """清理内存状态，仅用于测试隔离。"""

        self._conditions.clear()


agent_run_event_broker = AgentRunEventBroker()
