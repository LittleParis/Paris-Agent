"""P1 进程内 SSE 事件 Broker。

该实现用于跑通最小闭环：事件仅存在当前 API 进程内，服务重启后会丢失，也不能支持
多实例共享。后续阶段将由 runtime_events 持久化并通过 RabbitMQ 分发。
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.schemas.agent import AgentRunEvent, AgentRunEventType, AgentRunStatus


TERMINAL_EVENTS = {"run.completed", "run.failed"}


class AgentRunEventBroker:
    """按 run_id 保存事件历史，并唤醒等待中的 SSE 消费者。"""

    def __init__(self) -> None:
        self._events: dict[uuid.UUID, list[AgentRunEvent]] = {}
        self._conditions: dict[uuid.UUID, asyncio.Condition] = {}

    def _condition_for(self, run_id: uuid.UUID) -> asyncio.Condition:
        """每个 Run 使用独立 Condition，避免无关 Run 互相唤醒。"""

        return self._conditions.setdefault(run_id, asyncio.Condition())

    async def publish(
        self,
        *,
        run_id: uuid.UUID,
        event_type: AgentRunEventType,
        status: AgentRunStatus,
        node_name: str | None = None,
        delta: str | None = None,
        output: str | None = None,
        error_message: str | None = None,
    ) -> AgentRunEvent:
        """追加事件、分配单调递增序号，并通知 SSE 连接。"""

        condition = self._condition_for(run_id)
        async with condition:
            history = self._events.setdefault(run_id, [])
            event = AgentRunEvent(
                event_type=event_type,
                run_id=run_id,
                sequence=len(history) + 1,
                timestamp=datetime.now(UTC),
                status=status,
                node_name=node_name,
                delta=delta,
                output=output,
                error_message=error_message,
            )
            history.append(event)
            condition.notify_all()
            return event

    async def stream(self, run_id: uuid.UUID) -> AsyncIterator[AgentRunEvent]:
        """按顺序回放已有事件，并等待新事件直到 Run 结束。"""

        condition = self._condition_for(run_id)
        next_index = 0
        while True:
            async with condition:
                history = self._events.setdefault(run_id, [])
                while next_index >= len(history):
                    # 使用条件等待而不是轮询，空闲时不会持续占用 CPU。
                    await condition.wait()
                event = history[next_index]
                next_index += 1
            yield event
            if event.event_type in TERMINAL_EVENTS:
                return

    def clear(self) -> None:
        """清理内存状态，仅用于测试隔离。"""

        self._events.clear()
        self._conditions.clear()


agent_run_event_broker = AgentRunEventBroker()
