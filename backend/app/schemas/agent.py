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

    # 会话线程 ID：同一个 thread 下的多次 Run 共享上下文（P1 暂未使用，传 null 即可）
    thread_id: uuid.UUID | None = None
    # 项目 ID：将 Run 关联到某个具体项目，方便按项目维度查询记忆和知识（P1 暂未使用）
    project_id: uuid.UUID | None = None
    # Skill 标识：显式指定要调用哪个 Skill（如 "tech_qa"），不传则由 Skill Router 自动路由
    skill_id: str | None = Field(default=None, max_length=128)
    # 任务类型：区分不同场景（"chat"=普通问答，未来还有 "learning_path"、"rag_eval" 等）
    task_type: str = Field(default="chat", min_length=1, max_length=64)
    # 用户输入的问题或指令，必填，不能为空或纯空白字符
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

    # 本次 Run 的唯一业务标识（UUID），后续所有查询和 SSE 都靠它定位
    run_id: uuid.UUID
    # 创建后立即返回的初始状态，固定为 "queued"
    status: AgentRunStatus
    # Run 在数据库中的创建时间（带时区），由数据库 server_default=now() 生成
    created_at: datetime
    # 查询 Run 详情的相对 URL，如 "/api/agent/runs/{run_id}"，同时写入 HTTP Location 头
    detail_url: str
    # SSE 事件流的相对 URL，如 "/api/agent/runs/{run_id}/events"，前端用它建立长连接
    events_url: str


class AgentRunRead(BaseModel):
    """GET 返回的最新 Run 状态快照。"""

    # 允许从 ORM 对象直接构造（SQLAlchemy Model → Pydantic），无需手动逐字段赋值
    model_config = ConfigDict(from_attributes=True)

    # 本次 Run 的唯一业务标识（UUID），对外暴露，API 路径和 SSE 都引用它
    run_id: uuid.UUID
    # 会话线程 ID，同一 thread 的多次 Run 共享上下文（P1 阶段通常为 null）
    thread_id: uuid.UUID | None
    # 发起 Run 的用户 ID，P1 从后端 DEFAULT_USER_ID 读取，后续改为认证上下文
    user_id: uuid.UUID
    # 关联的项目 ID，用于按项目维度聚合记忆和知识（P1 阶段通常为 null）
    project_id: uuid.UUID | None
    # 实际执行的 Skill 标识（如 "tech_qa"），P1 阶段通常为 null，P2 接入 Skill Router 后才有值
    skill_id: str | None
    # 任务类型（"chat"、"learning_path" 等），决定走哪条执行链路
    task_type: str
    # 当前 Run 状态，取值见 AgentRunStatus
    status: AgentRunStatus
    # 当前正在执行的 DAG 节点名称（如 "mock_executor"），Run 结束后为 null
    current_node: str | None
    # 用户原始输入的问题或指令
    input: str
    # Agent 最终回复内容，只在 status="succeeded" 时有值
    final_output: str | None
    # 失败时的异常信息，只在 status="failed" 时有值
    error_message: str | None
    # 本次 Run 累计消耗的 LLM token 数（输入 + 输出），P1 Mock 固定返回 32
    total_tokens: int
    # 本次 Run 的累计成本（定点数，避免浮点精度漂移），P1 Mock 固定返回 0
    total_cost: Decimal
    # Run 记录的创建时间（带时区）
    created_at: datetime
    # Run 记录的最后更新时间（带时区），每次 update_state 时由 SQLAlchemy onupdate 刷新
    updated_at: datetime

    @field_serializer("total_cost")
    def serialize_total_cost(self, value: Decimal) -> str:
        # JSON number 会丢失 Decimal 精度，因此使用固定 8 位小数字符串。
        return f"{value:.8f}"


AgentRunEventType = Literal[
    "run.started",       # Run 开始执行，状态从 queued 变为 running
    "node.started",      # 某个 DAG 节点开始执行（如 memory_retriever、hybrid_search）
    "message.delta",     # LLM 流式输出的一个文本片段，前端拼接后形成完整回复
    "node.completed",    # 某个 DAG 节点执行完成，output 中携带节点结果
    "run.completed",     # 整个 Run 执行成功，output 中携带最终回复
    "run.failed",        # 整个 Run 执行失败，error_message 中携带异常信息
]


class AgentRunEvent(BaseModel):
    """所有 SSE 事件共享的统一信封结构。"""

    # 事件类型，前端根据它决定渲染逻辑（追加文本 / 更新节点状态 / 显示错误）
    event_type: AgentRunEventType
    # 该事件属于哪次 Run，前端用 run_id 将事件分发到正确的 Run 视图
    run_id: uuid.UUID
    # 事件序号（从 1 开始单调递增），用于 SSE 断线重连时的去重和顺序恢复
    sequence: int
    # 事件产生的时间戳（UTC），用于前端 TraceTimeline 的时间轴排序
    timestamp: datetime
    # 事件产生时 Run 的当前状态，前端用它更新 Run 状态指示器
    status: AgentRunStatus
    # 产生该事件的 DAG 节点名称（如 "mock_executor"），仅 node 类事件有值
    node_name: str | None = None
    # LLM 流式输出的文本片段，仅 message.delta 事件有值，前端拼接展示打字效果
    delta: str | None = None
    # 节点或 Run 的最终输出，仅 node.completed / run.completed 事件有值
    output: str | None = None
    # 失败时的异常信息，仅 run.failed 事件有值
    error_message: str | None = None
