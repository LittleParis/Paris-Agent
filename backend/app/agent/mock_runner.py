"""P1 Mock Agent Runner。

它模拟未来 Harness 的异步执行行为，让 API、数据库状态和 SSE 在尚未接入 LangGraph、
Skill、工具系统之前形成可验证闭环。
"""

import asyncio
import uuid
from decimal import Decimal

from app.agent.events import AgentRunEventBroker, agent_run_event_broker
from app.core.config import get_settings
from app.db.repositories.agent_runs import AgentRunRepository
from app.db.session import async_session_factory


MOCK_OUTPUT = "这是 Paris Agent 的模拟回复。"


class MockAgentRunner:
    """在当前 FastAPI 进程中异步推进 Agent Run。"""

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

    async def run(self, run_id: uuid.UUID) -> None:
        """执行固定 mock 流程并同步更新数据库与事件流。"""

        settings = get_settings()
        node_name = "mock_executor"
        try:
            async with async_session_factory() as session:
                # 后台任务拥有独立 Session，不能使用创建请求已经关闭的 Session。
                repository = AgentRunRepository(session)
                run = await repository.get_by_run_id(run_id)
                if run is None:
                    return

                await repository.update_state(
                    run,
                    status="running",
                    current_node=node_name,
                )
                await self.event_broker.publish(
                    run_id=run_id,
                    event_type="run.started",
                    status="running",
                    node_name=node_name,
                )
                await self.event_broker.publish(
                    run_id=run_id,
                    event_type="node.started",
                    status="running",
                    node_name=node_name,
                )

                for delta in ("这是 Paris Agent ", "的模拟回复。"):
                    # 分片事件模拟未来 LLM token streaming。
                    await asyncio.sleep(settings.mock_run_step_delay_seconds)
                    await self.event_broker.publish(
                        run_id=run_id,
                        event_type="message.delta",
                        status="running",
                        node_name=node_name,
                        delta=delta,
                    )

                await self.event_broker.publish(
                    run_id=run_id,
                    event_type="node.completed",
                    status="running",
                    node_name=node_name,
                    output=MOCK_OUTPUT,
                )
                await repository.update_state(
                    run,
                    status="succeeded",
                    current_node=None,
                    final_output=MOCK_OUTPUT,
                    total_tokens=32,
                    total_cost=Decimal("0"),
                )
                await self.event_broker.publish(
                    run_id=run_id,
                    event_type="run.completed",
                    status="succeeded",
                    output=MOCK_OUTPUT,
                )
        except Exception as exc:
            # Runner 的异常必须落到 Run 状态，并通过终止事件结束 SSE 连接。
            async with async_session_factory() as session:
                repository = AgentRunRepository(session)
                run = await repository.get_by_run_id(run_id)
                if run is not None:
                    await repository.update_state(
                        run,
                        status="failed",
                        current_node=None,
                        error_message=str(exc),
                    )
            await self.event_broker.publish(
                run_id=run_id,
                event_type="run.failed",
                status="failed",
                error_message=str(exc),
            )


mock_agent_runner = MockAgentRunner(agent_run_event_broker)
