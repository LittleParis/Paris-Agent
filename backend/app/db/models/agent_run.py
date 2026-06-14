"""Agent Run 的持久化状态快照。

该表只保存一次 Run 的当前状态和最终结果。步骤、节点、工具调用与运行事件会在后续
阶段进入各自的明细表，避免把不断增长的执行历史塞进一条频繁更新的记录。
"""

# ---------- 标准库 ----------
import uuid                          # 生成 UUID 业务标识（run_id 等）
from datetime import datetime        # 时间戳类型标注
from decimal import Decimal          # 成本字段用定点数，避免浮点精度漂移

# ---------- SQLAlchemy 核心类型 ----------
from sqlalchemy import (
    BigInteger,       # BIGINT：内部自增主键、token 计数等大整数场景
    CheckConstraint,  # CHECK 约束：在数据库层面兜底校验字段取值
    DateTime,         # TIMESTAMP 类型，配合 timezone=True 使用带时区时间
    Identity,         # GENERATED ALWAYS AS IDENTITY：PostgreSQL 推荐的自增主键写法
    Index,            # 显式声明索引，包括部分索引（WHERE 子句过滤）
    Integer,          # INTEGER：SQLite 测试时 BigInteger 退化为 Integer 才能自增
    Numeric,          # NUMERIC(p, s)：定点数，用于成本字段
    Text,             # TEXT：优先使用 TEXT 而非 VARCHAR(n)，遵循项目数据库规范
    Uuid,             # UUID 类型：PostgreSQL 原生 uuid，SQLite 测试时自动降级为 CHAR
    func,             # SQL 函数引用，这里用于 func.now() 获取数据库当前时间
    text,             # 原始 SQL 片段，用于 Index 的 postgresql_where 和表达式索引
)
# ---------- SQLAlchemy ORM 映射 ----------
from sqlalchemy.orm import Mapped, mapped_column  # 类型安全的列声明方式

from app.db.base import Base  # 声明式基类，所有 Model 都要继承它


# Run 合法状态值的常量元组，供代码中做 "if status in RUN_STATUSES" 校验。
# 数据库层面由 CHECK 约束兜底，这里给应用层代码也提供一份单一事实来源。
RUN_STATUSES = (
    "queued",              # 已入库，等待 Runner 拉取
    "running",             # Runner 正在执行
    "succeeded",           # 执行成功
    "failed",              # 执行失败
    "cancelled",           # 被取消
    "waiting_approval",    # 等待高风险工具审批
)


class AgentRun(Base):
    """一次 Agent 执行的主记录（状态快照）。

    只保存当前状态和最终结果，不保存过程细节。
    步骤、节点状态、工具调用、SSE 事件分别在 agent_steps、agent_node_states、
    agent_tool_calls、runtime_events 等明细表中，避免单行频繁 UPDATE。
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        # ===== CHECK 约束：数据库层面的最后一道防线 =====
        # 即使 Pydantic 校验被绕过，数据库也会拒绝非法值。

        # 状态必须属于预定义的合法值集合
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled', 'waiting_approval')",
            name="ck_agent_runs_status",
        ),
        # 用户输入不能是空白字符串（trim 后长度必须 > 0）
        CheckConstraint(
            "length(trim(input)) > 0",
            name="ck_agent_runs_input_not_blank",
        ),
        # token 消耗不能为负数（防止代码 bug 导致异常值入库）
        CheckConstraint(
            "total_tokens >= 0",
            name="ck_agent_runs_total_tokens",
        ),
        # 成本不能为负数
        CheckConstraint(
            "total_cost >= 0",
            name="ck_agent_runs_total_cost",
        ),

        # ===== 索引：加速高频查询 =====

        # 普通索引：按用户查历史 Run（"我的 Run 列表"页面，按时间倒序）
        Index(
            "ix_agent_runs_user_created",
            "user_id",
            text("created_at DESC"),
        ),
        # 以下三个是部分索引（Partial Index），只索引满足 WHERE 条件的行。
        # 好处：索引更小、写入成本更低，因为大部分 Run 最终会变成 succeeded/failed，
        # 而查询通常只关心"有值的"或"还在活跃的"数据。

        # 部分索引：只索引 thread_id 不为空的 Run（用于"查看某个会话线程的 Run 列表"）
        Index(
            "ix_agent_runs_thread_created",
            "thread_id",
            text("created_at DESC"),
            postgresql_where=text("thread_id IS NOT NULL"),
        ),
        # 部分索引：只索引 project_id 不为空的 Run（用于"查看某个项目的 Run 列表"）
        Index(
            "ix_agent_runs_project_created",
            "project_id",
            text("created_at DESC"),
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        # 部分索引：只索引还在活跃状态的 Run（用于后台 Worker 拉取待处理的 Run）
        # succeeded/failed/cancelled 的 Run 不需要被 Worker 扫描，所以排除在外
        Index(
            "ix_agent_runs_status_created",
            "status",
            "created_at",
            postgresql_where=text(
                "status IN ('queued', 'running', 'waiting_approval')"
            ),
        ),
    )

    # ===== 双主键策略 =====
    # id   → 数据库内部自增主键，只用于表间 JOIN 和内部排序，不对外暴露
    # run_id → UUID 业务标识，暴露给 API 和前端，所有外部查询都通过它

    # 内部主键：PostgreSQL 用 BIGINT IDENTITY（比 BIGSERIAL 更规范），
    # SQLite 测试时退化为 INTEGER 才能正常自增。
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )

    # 业务标识：由 uuid.uuid4 自动生成，UNIQUE 约束防止碰撞，
    # API 路径 /api/agent/runs/{run_id} 和 SSE 事件中的 run_id 都是它。
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )

    # 会话线程 ID：同一个 thread 下的多次 Run 共享上下文。
    # 例如用户在同一个对话窗口连续提问，每次提问是一个 Run，但都属于同一个 thread。
    # P1 阶段暂未实现会话管理，传 null。
    thread_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    # 用户 ID：谁发起的这次 Run。P1 从 .env 的 DEFAULT_USER_ID 读取，
    # 后续接入认证系统后从 JWT / Session 中获取。NOT NULL，每次 Run 必须有归属用户。
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    # 项目 ID：将 Run 关联到某个项目，方便按项目维度聚合记忆和知识检索。
    # 用户直接提问时可以为 null。
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    # 执行的 Skill 标识（如 "tech_qa"、"learning_path"）。
    # P1 阶段为 null；P2 接入 Skill Router 后由 Router 填入匹配到的 Skill ID。
    skill_id: Mapped[str | None] = mapped_column(Text)

    # 任务类型：区分不同的执行场景。
    # default / server_default 都设为 "chat"，保证 Python 层和数据库层默认值一致。
    # 未来会扩展为 "learning_path"、"rag_eval"、"code_sandbox" 等。
    task_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="chat",           # Python 层默认值（ORM 构造对象时）
        server_default="chat",    # 数据库层默认值（直接 INSERT SQL 时）
    )

    # 当前状态：取值受上方 CHECK 约束保护。
    # 状态迁移路径：queued → running → succeeded / failed / cancelled / waiting_approval
    # default / server_default 都为 "queued"，新创建的 Run 默认排队中。
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="queued",
        server_default="queued",
    )

    # 当前正在执行的 DAG 节点名称（如 "memory_retriever"、"hybrid_search"）。
    # Runner 每切换一个节点就 UPDATE 一次这个字段，前端用它展示"正在执行哪一步"。
    # Run 结束后置为 null。
    current_node: Mapped[str | None] = mapped_column(Text)

    # 用户输入：原始问题或指令，NOT NULL 且受 CHECK 约束不能为空白。
    input: Mapped[str] = mapped_column(Text, nullable=False)

    # 最终回复：只在 status="succeeded" 时有值，是 Agent 给用户的最终答案。
    # P1 Mock Runner 固定返回 "这是 Paris Agent 的模拟回复。"
    final_output: Mapped[str | None] = mapped_column(Text)

    # 错误信息：只在 status="failed" 时有值，记录 Runner 捕获的异常字符串。
    # 用于开发者排查问题和前端展示错误提示。
    error_message: Mapped[str | None] = mapped_column(Text)

    # 累计 token 消耗（输入 token + 输出 token）。
    # P1 Mock 固定写 32；未来接入 LLM 后由 Runner 从 API 响应中累加。
    # 使用 BigInteger 以防长对话累积超过 INTEGER 上限。
    total_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )

    # 累计成本（美元），使用 NUMERIC(18,8) 定点数。
    # 不用 FLOAT 是因为浮点数会产生累积精度误差，比如 0.1 + 0.2 != 0.3。
    # 18 位总精度、8 位小数，足以覆盖单次调用 $0.00000001 到 $9999999999.99 的范围。
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    # 创建时间：由数据库 server_default=now() 在 INSERT 时自动生成，Python 代码不手动赋值。
    # timezone=True 表示存储为带时区的 TIMESTAMPTZ，避免时区歧义。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 最后更新时间：INSERT 时由 server_default=now() 初始化，
    # 每次 UPDATE 时由 SQLAlchemy 的 onupdate=func.now() 自动刷新为当前时间。
    # 如果后续出现多个独立进程同时写同一行（如多 Worker 并发更新 Run 状态），
    # 可改为数据库触发器来保证原子性。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
