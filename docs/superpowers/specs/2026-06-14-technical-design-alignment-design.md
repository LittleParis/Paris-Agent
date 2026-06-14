# Paris Agent 技术设计文档对齐规格

## 1. 目标

本次工作只调整设计文档，不修改前端、后端、Docker Compose、数据库结构或
Alembic Migration。

目标是建立一套可以持续指导 P0-P16 实现的文档基线，消除以下高风险冲突：

- `AGENTS.md` 与技术设计文档的阶段编号不一致。
- 文档中的 Agent Run 状态、字段和 API 与已经实现的 P2 后端不一致。
- 数据库概念 SQL 缺少 PostgreSQL 必需的类型、约束、外键和索引规范。
- LangGraph、自研 DAG Runtime 与 Agent Harness 的职责重叠。
- SSE、RabbitMQ、跨存储同步和前端状态管理缺少可靠性契约。
- 未来能力、当前能力和阶段验收标准混在同一层级。

文档不能保证未来实现绝对不会出错，但必须让冲突可以在编码前被发现，并为每个
阶段设置可验证的完成门槛。

## 2. 文档权威层级

发生冲突时，按以下顺序处理：

1. `AGENTS.md`：项目定位、技术栈、目录、开发流程和 P0-P16 阶段顺序。
2. `docs/FULLSTACK_TECH_DESIGN.md`：总体架构、模块职责和跨阶段统一契约。
3. 专项契约文档：阶段或领域的详细请求、响应、事件和数据模型。
4. SQLAlchemy Model、Alembic Migration、Pydantic Schema 和 OpenAPI：已经实现功能
   的运行事实。

当第 3 层文档与第 4 层已实现事实冲突时，必须先判断代码是否符合第 1、2 层约束。
若代码正确，则更新专项文档；若代码错误，则单独提出代码修复任务，不能用文档
静默覆盖实现问题。

本次保持 `AGENTS.md` 稳定。只有发现其内部存在无法通过主设计文档解释的直接矛盾时，
才允许对其做最小修改并在变更摘要中单独说明。

## 3. 修改范围

### 3.1 必须更新

- `docs/FULLSTACK_TECH_DESIGN.md`
- `docs/P1_AGENT_RUN_CONTRACT.md`
- `docs/DATABASE_SCHEMA_REVISION_STRATEGY.md`

### 3.2 新增内容

主设计文档新增或重构以下规范：

- 当前状态、目标状态和非目标。
- 模块职责与依赖方向。
- LangGraph、DAG Runtime、Harness 的职责边界。
- ID、时间、状态、命名和金额规范。
- PostgreSQL 表设计与迁移规范。
- REST API、错误、分页、认证和幂等规范。
- SSE 顺序、去重、心跳、重连和终止规范。
- RabbitMQ 消息信封、ACK、重试、DLQ 和消费者幂等规范。
- PostgreSQL、Redis、RabbitMQ、Milvus、Elasticsearch、Neo4j 的数据所有权。
- Pinia、TanStack Query、Axios 和 EventSource 的前端职责。
- 安全、审计、配置和秘密管理规范。
- 测试层级、Migration 验证和阶段验收门槛。
- P0-P16 分步骤需求实现菜单。

### 3.3 不在本次范围

- 不修改任何应用代码。
- 不执行数据库结构变更。
- 不生成新的 Alembic Migration。
- 不添加前端页面或依赖。
- 不接入 LangGraph、Celery、Milvus、Elasticsearch、Neo4j 或 Docker Sandbox。
- 不为尚未进入阶段的模块编写可直接运行的完整实现。

## 4. 主设计文档结构

`FULLSTACK_TECH_DESIGN.md` 调整为以下结构：

1. 文档用途、权威层级与状态标记
2. 项目定位、目标与非目标
3. 当前实现基线
4. 技术栈和依赖管理
5. 总体架构与模块依赖
6. 核心业务场景
7. Skill 系统
8. Agent Runtime、LangGraph 与 Harness
9. 长期记忆
10. RAG 与多存储数据所有权
11. Tool Registry 与安全
12. RabbitMQ 与 Celery
13. 数据库统一规范与领域表清单
14. API 统一规范与领域 API
15. SSE 和 Runtime Event
16. 前端架构、页面和状态管理
17. 可观测性与成本
18. 测试、迁移和发布验证
19. P0-P16 分步骤需求菜单
20. Codex 任务模板

大型建表 SQL 不继续作为主文档中的唯一数据模型。主文档记录字段原则、关系、
约束和索引访问路径；已实现表以 Model 和 Migration 为准，未来表在专项数据库设计
确认后才能创建 Migration。

## 5. 统一架构边界

后端保持模块化单体，不提前拆微服务。业务依赖方向为：

```text
API / Queue Consumer
        ↓
Application Use Case
        ↓
Domain Policy / Runtime Contract
        ↓
Repository / Tool / Model / Queue Port
        ↓
Infrastructure Adapter
```

FastAPI 路由只负责协议解析、依赖注入、调用用例和响应映射。业务流程不能长期堆积在
路由或 SQLAlchemy Model 中。

运行时职责固定为：

- LangGraph：高层状态图、暂停恢复入口和 Checkpoint 集成。
- DAG Runtime：DAG 校验、依赖解析、拓扑调度和并行节点执行。
- Agent Harness：Run 生命周期、超时、重试、Fallback、工具隔离、事件、Trace 和成本。
- Skill Executor：把 Skill 配置和输入转换为经过校验的执行计划，不直接执行外部工具。
- Tool Manager：所有工具调用的唯一入口，负责权限、风险、审批、执行和审计。

P2 Mock Runner 明确标注为临时进程内实现，不能被描述为生产运行时。

## 6. 统一数据契约

### 6.1 标识

- 数据库内部主键：`BIGINT GENERATED ALWAYS AS IDENTITY`。
- 对外业务标识：PostgreSQL `UUID`。
- 固定配置标识，例如 `skill_id` 和 `tool_name`：受长度和格式约束的 `TEXT`。
- 同一关联链必须统一引用内部 ID 或业务 UUID，不能无说明地混用。

### 6.2 时间和数值

- 事件和业务时间统一使用 `TIMESTAMPTZ NOT NULL`。
- 创建时间默认 `now()`。
- 成本统一使用 `NUMERIC(18, 8)`，API 序列化为定点字符串。
- token 和累计计数使用非负 `BIGINT`。
- 延迟使用非负 `INTEGER` 毫秒值。

### 6.3 Agent Run 状态

统一使用：

```text
queued
running
waiting_approval
succeeded
failed
cancelled
```

禁止在同一资源中混用 `success` 与 `succeeded`。节点和工具状态可以拥有各自状态集合，
但必须在专项契约中定义状态迁移。

### 6.4 JSONB

JSONB 只保存可扩展配置、输入输出快照和事件载荷。核心关系和高频查询字段必须使用
普通列。JSONB 需要对象或数组类型约束，只有存在实际查询路径时才添加 GIN 索引。

## 7. 数据库设计策略

主设计文档列出领域表及其阶段，不要求 P2 一次创建全部表。

必须纳入最终模型的基础领域包括：

- Identity：`users`
- Project：`projects`、`project_members`
- Conversation：`chat_threads`、`chat_messages`
- Runtime：`agent_runs`、`runtime_events`、`agent_node_states`、
  `agent_tool_calls`、`agent_checkpoints`
- Skill：`agent_skills`、`agent_skill_versions`、`agent_skill_runs`
- Memory：`agent_memories`
- Knowledge：`documents`、`document_chunks`
- Audit：`audit_logs`
- Evaluation：`rag_eval_tasks`、`rag_eval_results`

`agent_steps` 不作为默认必建表。只有明确其与 `agent_node_states` 的不同用途后才创建，
避免重复保存同一节点执行历史。

所有表设计必须明确：

- 必填字段和默认值。
- 状态与数值 CHECK。
- 唯一约束。
- 外键、删除策略和外键索引。
- API 查询需要的组合索引。
- 数据保留和删除规则。

每次新增表都必须经过 Model、Migration、人工检查、upgrade、downgrade 和测试数据库
重建验证。

## 8. API 与错误规范

现阶段保留 `/api/...` 路径，不为尚未发布的内部 API 强制迁移到 `/api/v1`。首次形成
外部稳定契约前确定版本策略。

规范包括：

- 资源使用复数名词。
- 异步创建返回 `202 Accepted` 和 `Location`。
- GET 不产生副作用。
- 列表接口采用游标分页，并定义 `limit` 上限。
- 创建类接口在可能重试时支持 `Idempotency-Key`。
- `user_id` 由认证上下文提供，不能信任客户端任意提交。
- 成功响应直接返回资源或分页集合，不强制套统一业务信封。
- 错误响应统一使用 RFC 7807 风格 Problem Details。
- Validation、Not Found、Conflict、Unauthorized、Forbidden 和内部错误有稳定错误码。

历史文件名为 P1 的 Agent Run 契约保持当前 P2 已实现字段和 `202` 行为，不在文档
对齐任务中制造破坏性变更。

## 9. SSE 事件规范

统一事件信封至少包含：

```text
event_id
event_type
run_id
sequence
timestamp
status
payload
```

P2 已实现的扁平字段暂时兼容。进入 `runtime_events` 阶段时，再通过专项迁移设计转为
稳定信封，不能直接破坏现有前端。

可靠性规则：

- 同一 Run 的 `sequence` 从 1 单调递增并有唯一约束。
- SSE `id` 对应可恢复的事件序号或事件 ID。
- 客户端使用 `Last-Event-ID` 恢复，服务端按缺失位置回放。
- 长连接定期发送注释心跳。
- 客户端按事件 ID 去重。
- `run.completed`、`run.failed`、`run.cancelled` 是终止事件。
- 事件先持久化，再发布；RabbitMQ 不能作为唯一事件存储。
- P2 进程内 Broker 明确不支持重启恢复和多实例。

## 10. RabbitMQ 与跨存储一致性

消息统一包含：

```text
message_id
message_type
schema_version
occurred_at
correlation_id
causation_id
idempotency_key
payload
```

消费者成功提交数据库事务后 ACK。失败按可重试和不可重试分类；重试达到上限进入 DLQ。
所有消费者必须按 `message_id` 或业务幂等键去重。

需要同时写数据库和发布消息的流程采用 Transactional Outbox，不能依赖“先提交数据库，
再直接 publish”的双写顺序保证一致性。

数据所有权固定为：

- PostgreSQL：业务事实、状态、引用关系、审计和外部索引同步状态。
- Redis：缓存、短期锁、限流和可丢失的临时状态。
- RabbitMQ：消息传递，不是长期事实存储。
- Milvus：向量及向量索引。
- Elasticsearch：Chunk 的稀疏检索索引。
- Neo4j：知识实体、关系和图检索投影。

外部索引必须可由 PostgreSQL 元数据重建，并保存同步状态、索引版本、最后同步时间和
失败原因。

## 11. 前端职责

- Axios Client：REST 请求、基础 URL、超时和错误转换。
- TanStack Query：服务端查询缓存、失效和重试。
- Pinia：当前会话、正在运行的 Run、SSE 增量、用户选择和页面交互状态。
- EventSource 封装：SSE 建连、事件解析、去重、重连和关闭。
- Vue 页面和组件不直接拼接请求 URL。

P3 ChatPage 保留当前 Workbench 视觉样式，新增 `/chat`，不重做 Dashboard。开发环境通过
Vite 同源代理访问后端，避免本次为联调引入后端 CORS 变更。

## 12. 分阶段需求菜单格式

主文档中的 P0-P16 必须严格对齐 `AGENTS.md`。每个阶段均包含：

- 阶段目标。
- 当前状态。
- 前置依赖。
- 后端需求。
- 前端需求。
- 数据库与 Migration。
- API、SSE 或消息契约。
- 自动测试与手动验证。
- 完成标准。
- 明确不做的内容。

当前状态基线：

- P0：项目骨架已完成。
- P1：health check 与前端基础布局已完成。
- P2：后端 Agent Run Mock 已完成。
- P3：前端 ChatPage 联调进行中。
- P4：后端进程内 SSE 已部分实现。
- P5-P16：未开始，除非专项契约明确标注已有部分实现。

阶段验收遵循“前一阶段可运行、可验证、契约稳定后再进入下一阶段”，但允许提前编写
不会触发实现的设计文档。

## 13. 验证方法

文档修改后执行以下检查：

1. 搜索旧品牌 `AGI Assistant` 和旧包名。
2. 搜索冲突状态 `success` 与 `succeeded`。
3. 搜索 `BIGSERIAL`、无时区 `TIMESTAMP` 和概念性 `VARCHAR` 建表语句。
4. 对比 `AGENTS.md` 与主文档的 P0-P16 名称和顺序。
5. 对比历史文件名为 P1 的 Agent Run 文档与 P2 Pydantic Schema、路由、Model 和
   Migration。
6. 检查 API、SSE、数据库和前端类型中的同名字段。
7. 搜索 `TODO`、`TBD`、未定义缩写和互相矛盾的状态迁移。
8. 检查 Markdown 标题层级、代码块和内部链接。
9. 使用 `git diff --check` 检查空白与格式问题。

## 14. 完成标准

本次文档对齐完成必须同时满足：

- 三份目标文档没有相互矛盾的 Agent Run 契约。
- P0-P16 与 `AGENTS.md` 完全一致。
- 当前能力和未来能力有明确状态标签。
- 数据库章节不再鼓励不符合项目规范的 PostgreSQL SQL。
- LangGraph、DAG Runtime、Harness 和 Tool Manager 职责不重叠。
- API、SSE、消息和跨存储同步拥有最低可靠性规则。
- 每个阶段都可以独立转化为一份小范围 Codex 实现任务。
- 没有修改任何应用代码或数据库。
