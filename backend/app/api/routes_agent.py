"""Agent Run HTTP 与 SSE 路由。"""

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner
from app.core.config import get_settings
from app.db.repositories.agent_runs import AgentRunRepository
from app.db.session import get_session
from app.schemas.agent import AgentRunCreate, AgentRunCreated, AgentRunRead


router = APIRouter(prefix="/api/agent/runs", tags=["agent-runs"])


@router.post("", response_model=AgentRunCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_agent_run(
    payload: AgentRunCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AgentRunCreated:
    """持久化 queued Run，立即返回 202，再由 Mock Runner 异步执行。"""

    settings = get_settings()
    repository = AgentRunRepository(session)
    run = await repository.create(
        user_id=settings.default_user_id,
        input_text=payload.input,
        thread_id=payload.thread_id,
        project_id=payload.project_id,
        skill_id=payload.skill_id,
        task_type=payload.task_type,
    )
    detail_url = f"/api/agent/runs/{run.run_id}"
    events_url = f"{detail_url}/events"
    response.headers["Location"] = detail_url
    # 必须先提交数据库，再启动后台任务，确保 Runner 一定能查询到该 Run。
    mock_agent_runner.start(run.run_id)
    return AgentRunCreated(
        run_id=run.run_id,
        status="queued",
        created_at=run.created_at,
        detail_url=detail_url,
        events_url=events_url,
    )


@router.get("/{run_id}", response_model=AgentRunRead)
async def get_agent_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AgentRunRead:
    """返回当前状态快照，不在该接口中加载节点或事件明细。"""

    run = await AgentRunRepository(session).get_by_run_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return AgentRunRead.model_validate(run)


@router.get("/{run_id}/events")
async def stream_agent_run_events(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """回放并持续推送指定 Run 的 mock SSE 事件。"""

    run = await AgentRunRepository(session).get_by_run_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")

    async def event_stream() -> AsyncIterator[str]:
        async for event in agent_run_event_broker.stream(run_id):
            # 每条 SSE 消息以空行结束；event 字段便于前端按类型监听。
            yield (
                f"id: {event.sequence}\n"
                f"event: {event.event_type}\n"
                f"data: {event.model_dump_json()}\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
