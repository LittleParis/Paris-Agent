"""P4 Mock Agent Runner。

它模拟未来 Harness 的异步执行行为，让 API、数据库状态和 SSE 在尚未接入 LangGraph、
Skill、工具系统之前形成可验证闭环。

P4 变化：事件先持久化到 runtime_events 表，再通过进程内 Broker 唤醒 SSE 消费者。
"""

import asyncio
import uuid
from decimal import Decimal

from app.agent.events import AgentRunEventBroker, agent_run_event_broker
from app.core.config import get_settings
from app.db.repositories.agent_runs import AgentRunRepository
from app.db.repositories.runtime_events import RuntimeEventRepository
from app.db.session import async_session_factory
from app.schemas.agent import RuntimeEventPayload


MOCK_OUTPUT = "这是 Paris Agent 的模拟回复。"


class MockAgentRunner:
    """在当前 FastAPI 进程中异步推动 Agent Run。"""

    def __init__(self, event_broker: AgentRunEventBroker) -> None:
        self.event_broker = event_broker
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, run_id: uuid.UUID) -> None:
        """启动后台任务且保存引用，避免 Task 被垃圾回收。"""

        task = asyncio.create_task(self.run(run_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait_for_all(self) -> None:
        """等待所有后台任务结束，主要用于测试和优雅关闭。"""

        if self._tasks:
            await asyncio.gather(*tuple(self._tasks))

    async def _publish_event(
        self,
        session,
        *,
        run_id: uuid.UUID,
        event_type: str,
        status: str,
        payload: RuntimeEventPayload | None = None,
    ) -> None:
        """持久化事件到数据库，提交后再通知 Broker。

        发布顺序：
        1. INSERT runtime_events (在事务内锁定 Run 行)
        2. COMMIT
        3. Broker.notify(run_id)

        数据库提交失败时不得通知订阅者。
        通知失败不回滚已持久化事件。
        """

        repo = RuntimeEventRepository(session)
        await repo.append(
            run_id=run_id,
            event_type=event_type,
            status=status,
            payload=payload,
        )
        # commit 已在 repo.append 内完成
        try:
            await self.event_broker.notify(run_id)
        except Exception:
            # 通知失败不影响已持久化事件，SSE 后续可通过数据库回放获得
            pass

    async def run(self, run_id: uuid.UUID) -> None:
        """执行固定 mock 流程并同步更新数据库与事件流。"""

        settings = get_settings()
        node_name = "mock_executor"
        try:
            async with async_session_factory() as session:
                # 后台任务拥有独立 Session，不能使用创建请求已经关闭的 Session。
                run_repo = AgentRunRepository(session)
                run = await run_repo.get_by_run_id(run_id)
                if run is None:
                    return

                # run.started：先将 Run 状态更新为 running
                await run_repo.update_state(
                    run,
                    status="running",
                    current_node=node_name,
                )
                await self._publish_event(
                    session,
                    run_id=run_id,
                    event_type="run.started",
                    status="running",
                    payload=RuntimeEventPayload(node_name=node_name),
                )

                # node.started
                await self._publish_event(
                    session,
                    run_id=run_id,
                    event_type="node.started",
                    status="running",
                    payload=RuntimeEventPayload(node_name=node_name),
                )

                # message.delta × 2：模拟 LLM token streaming
                for delta in ("这是 Paris Agent ", "的模拟回复。"):
                    await asyncio.sleep(settings.mock_run_step_delay_seconds)
                    await self._publish_event(
                        session,
                        run_id=run_id,
                        event_type="message.delta",
                        status="running",
                        payload=RuntimeEventPayload(
                            node_name=node_name,
                            delta=delta,
                        ),
                    )

                # node.completed
                await self._publish_event(
                    session,
                    run_id=run_id,
                    event_type="node.completed",
                    status="running",
                    payload=RuntimeEventPayload(
                        node_name=node_name,
                        output=MOCK_OUTPUT,
                    ),
                )

                # run.completed：先将 Run 状态更新为 succeeded
                await run_repo.update_state(
                    run,
                    status="succeeded",
                    current_node=None,
                    final_output=MOCK_OUTPUT,
                    total_tokens=32,
                    total_cost=Decimal("0"),
                )
                await self._publish_event(
                    session,
                    run_id=run_id,
                    event_type="run.completed",
                    status="succeeded",
                    payload=RuntimeEventPayload(output=MOCK_OUTPUT),
                )
        except Exception as exc:
            # Runner 的异常必须落到 Run 状态，并通过终止事件结束 SSE 连接。
            async with async_session_factory() as session:
                run_repo = AgentRunRepository(session)
                run = await run_repo.get_by_run_id(run_id)
                if run is not None:
                    await run_repo.update_state(
                        run,
                        status="failed",
                        current_node=None,
                        error_message=str(exc),
                    )
                await self._publish_event(
                    session,
                    run_id=run_id,
                    event_type="run.failed",
                    status="failed",
                    payload=RuntimeEventPayload(error_message=str(exc)),
                )


mock_agent_runner = MockAgentRunner(agent_run_event_broker)
