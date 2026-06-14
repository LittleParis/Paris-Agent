"""Agent Run HTTP 与 SSE 路由。"""

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner
from app.core.config import get_settings
from app.db.repositories.agent_runs import AgentRunRepository
from app.db.repositories.runtime_events import RuntimeEventRepository
from app.db.session import async_session_factory, get_session
from app.schemas.agent import (
    AgentRunCreate,
    AgentRunCreated,
    AgentRunRead,
    RuntimeEventEnvelope,
    TERMINAL_EVENT_TYPES,
)


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


def _format_sse(envelope: RuntimeEventEnvelope) -> str:
    """将事件信封格式化为 SSE 文本帧。"""

    return (
        f"id: {envelope.event_id}\n"
        f"event: {envelope.event_type}\n"
        f"data: {envelope.model_dump_json()}\n\n"
    )


@router.get("/{run_id}/events")
async def stream_agent_run_events(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """回放并持续推送指定 Run 的 SSE 事件。

    支持数据库回放、Last-Event-ID 断线恢复、心跳和终止事件关闭。
    """

    # 验证 Run 存在
    run = await AgentRunRepository(session).get_by_run_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")

    # 解析 Last-Event-ID
    cursor_sequence = 0
    if last_event_id is not None:
        # UUID 格式非法时返回 400
        try:
            event_uuid = uuid.UUID(last_event_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Last-Event-ID must be a valid UUID",
            )

        # 事件不存在时返回 400
        event_repo = RuntimeEventRepository(session)
        cursor_event = await event_repo.get_by_event_id(event_uuid)
        if cursor_event is None:
            raise HTTPException(
                status_code=400,
                detail="Event referenced by Last-Event-ID not found",
            )

        # 事件不属于当前 Run 时返回 400
        if cursor_event.run_id != run_id:
            raise HTTPException(
                status_code=400,
                detail="Event does not belong to this run",
            )

        cursor_sequence = cursor_event.sequence

    async def event_stream() -> AsyncIterator[str]:
        """SSE 生成器：从数据库回放 + 进程内通知等待。"""

        heartbeat_timeout = get_settings().sse_heartbeat_seconds
        # 使用独立 Session，不依赖请求 Session（请求可能在流结束前关闭）
        async with async_session_factory() as sse_session:
            event_repo = RuntimeEventRepository(sse_session)
            current_sequence = cursor_sequence
            terminated = False

            while not terminated:
                # 先从数据库查询游标之后的事件
                events = await event_repo.list_after_sequence(
                    run_id, current_sequence
                )

                if events:
                    # 有事件：按序发送并推进游标
                    for event in events:
                        envelope = RuntimeEventRepository.to_envelope(event)
                        yield _format_sse(envelope)
                        current_sequence = envelope.sequence

                        if envelope.event_type in TERMINAL_EVENT_TYPES:
                            terminated = True
                            break
                else:
                    # 无事件：等待 Broker 通知，最长等待心跳间隔
                    notified = await agent_run_event_broker.wait_for_notification(
                        run_id,
                        timeout=heartbeat_timeout,
                    )
                    if not notified:
                        # 超时：发送 SSE 注释心跳
                        yield ": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
