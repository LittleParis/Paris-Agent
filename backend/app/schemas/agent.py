"""Agent Run API 的请求、响应与 SSE 事件契约。"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


AgentRunStatus = Literal[
    "queued",              # 已排队，等待后台 Runner 拉取执行
    "running",             # 正在执行中（Mock Runner 或未来的 Harness 正在跑）
    "succeeded",           # 执行成功，final_output 中有最终回复
    "failed",              # 执行失败，error_message 中有异常信息
    "cancelled",           # 用户或系统主动取消了本次 Run
    "waiting_approval",    # 高风险工具调用需要用户审批，Run 暂停等待
]


class AgentRunCreate(BaseModel):
    """创建 Run 的客户端输入。

    user_id 不允许由客户端提交；P1 从后端配置读取，后续改为认证上下文。
    """

    thread_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    skill_id: str | None = Field(default=None, max_length=128)
    task_type: str = Field(default="chat", min_length=1, max_length=64)
    input: str = Field(min_length=1)

    @field_validator("input")
    @classmethod
    def input_must_not_be_blank(cls, value: str) -> str:
        """去除首尾空白并拒绝只有空白字符的输入。"""

        value = value.strip()
        if not value:
            raise ValueError("input must not be blank")
        return value


class AgentRunCreated(BaseModel):
    """POST 创建成功后的轻量响应，不等待后台执行完成。"""

    run_id: uuid.UUID
    status: AgentRunStatus
    created_at: datetime
    detail_url: str
    events_url: str


class AgentRunRead(BaseModel):
    """GET 返回的最新 Run 状态快照。"""

    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    thread_id: uuid.UUID | None
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    skill_id: str | None
    task_type: str
    status: AgentRunStatus
    current_node: str | None
    input: str
    final_output: str | None
    error_message: str | None
    total_tokens: int
    total_cost: Decimal
    created_at: datetime
    updated_at: datetime

    @field_serializer("total_cost")
    def serialize_total_cost(self, value: Decimal) -> str:
        return f"{value:.8f}"


# ===== P4 稳定事件信封 =====

AgentRunEventType = Literal[
    "run.started",
    "node.started",
    "message.delta",
    "node.completed",
    "run.completed",
    "run.failed",
    "run.cancelled",
]

# 终止事件类型集合，SSE 发送后立即关闭连接
TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {"run.completed", "run.failed", "run.cancelled"}
)


class RuntimeEventPayload(BaseModel):
    """事件特有数据，始终为 JSON 对象。

    不同事件类型使用不同字段子集：
    - run.started:       { node_name? }
    - node.started:      { node_name }
    - message.delta:     { node_name?, delta }
    - node.completed:    { node_name, output? }
    - run.completed:     { output? }
    - run.failed:        { error_message }
    - run.cancelled:     { reason? }
    """

    node_name: str | None = None
    delta: str | None = None
    output: str | None = None
    error_message: str | None = None
    reason: str | None = None


class RuntimeEventEnvelope(BaseModel):
    """P4 稳定事件信封，统一用于 Pydantic、数据库、SSE JSON 和前端类型。"""

    # 事件 UUID，作为 SSE id 和全局去重标识
    event_id: uuid.UUID
    # 事件类型
    event_type: AgentRunEventType
    # 所属 Agent Run
    run_id: uuid.UUID
    # 同一 Run 内从 1 单调递增
    sequence: int
    # 数据库记录的 UTC 时间
    timestamp: datetime
    # 事件产生时的 Run 状态
    status: AgentRunStatus
    # 事件特有数据
    payload: RuntimeEventPayload
