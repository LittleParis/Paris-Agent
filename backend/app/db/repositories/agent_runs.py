"""Agent Run 数据访问层。

路由和 Runner 不直接拼接 SQL。后续增加事务、锁或查询优化时，只需集中修改
Repository，而不改变 API 契约。
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_run import AgentRun


class AgentRunRepository:
    """封装 agent_runs 表的最小读写操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        input_text: str,
        thread_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        skill_id: str | None,
        task_type: str,
    ) -> AgentRun:
        """创建 queued 状态的 Run，并返回数据库生成后的完整实体。"""

        run = AgentRun(
            user_id=user_id,
            thread_id=thread_id,
            project_id=project_id,
            skill_id=skill_id,
            task_type=task_type,
            input=input_text,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_by_run_id(self, run_id: uuid.UUID) -> AgentRun | None:
        """使用对外业务标识查询 Run。"""

        result = await self.session.execute(
            select(AgentRun).where(AgentRun.run_id == run_id)
        )
        return result.scalar_one_or_none()

    async def update_state(
        self,
        run: AgentRun,
        *,
        status: str,
        current_node: str | None,
        final_output: str | None = None,
        error_message: str | None = None,
        total_tokens: int | None = None,
        total_cost: Decimal | None = None,
    ) -> AgentRun:
        """原子提交一次 Run 状态快照更新。

        P1 只有单进程 Mock Runner。后续接入 Celery/多 Worker 后，需要在这里增加
        合法状态迁移校验和乐观锁，防止并发 Worker 覆盖新状态。
        """

        run.status = status
        run.current_node = current_node
        run.final_output = final_output
        run.error_message = error_message
        if total_tokens is not None:
            run.total_tokens = total_tokens
        if total_cost is not None:
            run.total_cost = total_cost
        await self.session.commit()
        await self.session.refresh(run)
        return run
