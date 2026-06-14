# P4 SSE 事件流设计规格

## 1. 任务目标

P4 将 P2 的进程内 Mock SSE 和 P3 的 REST 短轮询升级为可持久化、可回放、可断线恢复的事件流：

```text
创建 Agent Run
→ Mock Runner 推进状态
→ runtime_events 先持久化事件
→ 进程内通知唤醒 SSE
→ 前端通过 EventSource 增量消费
→ message.delta 拼接回复
→ 终止事件关闭连接
```

本阶段仍使用单进程 Mock Runner，不接入 RabbitMQ、Celery、LangGraph、完整 Harness 或多实例广播。

## 2. 相关文档

- `AGENTS.md`
- `docs/FULLSTACK_TECH_DESIGN.md`
- `docs/P1_AGENT_RUN_CONTRACT.md`
- `docs/superpowers/specs/2026-06-14-p3-chat-page-mock-design.md`

## 3. 本次范围

### 3.1 后端

- 新增 `runtime_events` SQLAlchemy Model 和 Alembic Migration。
- 将 SSE 事件迁移为稳定事件信封。
- 新增 Runtime Event Repository。
- 事件必须先提交数据库，再发送进程内通知。
- 同一 Run 的 `sequence` 从 1 单调递增。
- SSE 支持历史回放、`Last-Event-ID`、心跳和终止事件关闭。
- Mock Runner 使用持久化事件发布接口，不再把历史事件保存在内存中。
- 保留 `GET /api/agent/runs/{run_id}/events` 路径。

### 3.2 前端

- 新增原生 `EventSource` 封装。
- 创建 Run 后使用 SSE 替代 REST 短轮询。
- 支持 `message.delta` 增量显示。
- 使用 Run 和节点事件更新右侧 Runtime 面板。
- 显示当前 Run 的事件时间线。
- 支持原生自动重连、事件去重和页面卸载清理。

### 3.3 测试

- Runtime Event Model 和 Repository 测试。
- 事件顺序、持久化、回放和游标测试。
- 未知 Run、非法或不匹配的 `Last-Event-ID` 测试。
- SSE 终止关闭和事件信封测试。
- 前端 TypeScript/Vite 构建验证。
- 前端 SSE 去重逻辑使用可独立测试的纯函数或状态方法验证。

## 4. 明确不做

- RabbitMQ 或 Celery 事件分发。
- PostgreSQL `LISTEN/NOTIFY`。
- 多 API 实例共享实时通知。
- LangGraph、DAG Runtime、Checkpoint、Retry 或 Fallback。
- Skill、Memory、RAG、Tool、Sandbox 和审批流程。
- 会话历史持久化。
- 自定义 `fetch` 流解析器。
- 新增前端依赖。

## 5. 方案选择

采用“PostgreSQL 回放 + 进程内通知”。

PostgreSQL 是事件事实存储。进程内 Broker 只持有每个 Run 的 `asyncio.Condition`，用于减少同一实例内 SSE 对数据库的轮询，不保存事件历史，也不负责分配序号。

该方案满足 P4 的断线恢复目标，同时保持单实例实现简单。多实例实时通知留到 RabbitMQ 阶段。

## 6. 稳定事件信封

公共事件结构：

```json
{
  "event_id": "UUID",
  "event_type": "message.delta",
  "run_id": "UUID",
  "sequence": 3,
  "timestamp": "2026-06-14T00:00:00Z",
  "status": "running",
  "payload": {
    "node_name": "mock_executor",
    "delta": "这是 Paris Agent "
  }
}
```

字段规则：

- `event_id`：事件 UUID，作为 SSE `id` 和全局去重标识。
- `event_type`：事件类型。
- `run_id`：所属 Agent Run。
- `sequence`：同一 Run 内从 1 单调递增。
- `timestamp`：数据库记录的 UTC 时间。
- `status`：事件产生时的 Run 状态。
- `payload`：事件特有数据，始终为 JSON 对象。

P4 支持的事件类型：

```text
run.started
node.started
message.delta
node.completed
run.completed
run.failed
run.cancelled
```

`payload` 约定：

```text
run.started       { node_name? }
node.started      { node_name }
message.delta     { node_name?, delta }
node.completed    { node_name, output? }
run.completed     { output? }
run.failed        { error_message }
run.cancelled     { reason? }
```

后端 Pydantic 类型、数据库记录、SSE JSON 和前端 TypeScript 类型统一采用该信封，不保留旧扁平事件格式。

## 7. 数据结构

新增 `runtime_events`：

```text
id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
event_id    UUID NOT NULL UNIQUE
run_id      UUID NOT NULL
sequence    BIGINT NOT NULL
event_type  TEXT NOT NULL
status      TEXT NOT NULL
payload     JSONB NOT NULL DEFAULT '{}'
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```

约束和索引：

- 外键 `run_id → agent_runs.run_id`，`ON DELETE CASCADE`。
- 唯一约束 `UNIQUE (run_id, sequence)`。
- `sequence > 0`。
- `event_type` 非空白。
- `status` 必须属于 Agent Run 合法状态。
- `payload` 必须为 JSON 对象。
- 索引 `(run_id, sequence)` 由唯一约束提供。
- `event_id` 唯一索引用于恢复游标定位。

SQLite 测试环境使用 SQLAlchemy 可移植 JSON 类型，并为 PostgreSQL 映射为 JSONB。Migration 明确创建 PostgreSQL JSONB。

## 8. Repository 与事件发布

### 8.1 RuntimeEventRepository

职责：

- `append(...)`：创建并提交单条事件。
- `list_after_sequence(run_id, sequence)`：按升序查询缺失事件。
- `get_by_event_id(event_id)`：解析恢复游标。
- `get_last_sequence(run_id)`：辅助测试和诊断。

### 8.2 序号分配

生产 PostgreSQL 中，`append` 在事务内锁定所属 `agent_runs` 行，再查询当前最大 `sequence` 并加一。该锁将同一 Run 的并发发布串行化，不同 Run 之间互不阻塞。

SQLite 测试不支持等价的行级锁，但测试仅使用单进程顺序发布；数据库唯一约束仍负责拒绝重复序号。

### 8.3 发布顺序

```text
锁定 Run
→ 分配 sequence
→ INSERT runtime_events
→ COMMIT
→ Broker.notify(run_id)
```

数据库提交失败时不得通知订阅者。通知失败不回滚已持久化事件，SSE 后续仍可通过数据库回放获得该事件。

## 9. SSE 接口

接口保持：

```http
GET /api/agent/runs/{run_id}/events
```

消息格式：

```text
id: <event_id UUID>
event: <event_type>
data: <稳定事件信封 JSON>

```

响应头：

```text
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### 9.1 初次连接

- 验证 Run 存在，否则返回 `404`。
- 从 `sequence > 0` 开始按序回放所有已持久化事件。
- 回放结束后等待新事件通知。

### 9.2 Last-Event-ID

- 从 HTTP `Last-Event-ID` Header 读取事件 UUID。
- UUID 格式非法时返回 `400`。
- 事件不存在时返回 `400`。
- 事件不属于当前 Run 时返回 `400`。
- 找到事件后，仅发送 `sequence` 更大的事件。

浏览器原生 `EventSource` 重连时自动携带最近成功接收的 SSE `id`。

### 9.3 等待与心跳

SSE 循环每次先从数据库查询游标之后的事件：

- 有事件：按序发送并推进游标。
- 无事件：等待 Broker 通知，最长等待 15 秒。
- 15 秒无通知：发送 SSE 注释心跳 `: heartbeat`，随后继续查询。

Broker 通知只代表“数据库可能有新事件”，客户端仍以数据库查询结果为准。

### 9.4 终止事件

终止类型：

```text
run.completed
run.failed
run.cancelled
```

发送终止事件后立即结束该 Run 的 SSE 响应。若客户端在 Run 已结束后连接，服务端回放到终止事件后关闭。

## 10. Mock Runner

Mock Runner 保留当前模拟执行流程：

```text
run.started
node.started
message.delta
message.delta
node.completed
run.completed
```

变化：

- 使用 Runtime Event Publisher 写入数据库。
- Run 状态更新和对应事件写入保持明确顺序。
- `run.started` 前先将 Run 状态更新为 `running`。
- `run.completed` 前先将 Run 状态更新为 `succeeded`。
- 异常路径先尽力将 Run 更新为 `failed`，再发布 `run.failed`。
- 事件 payload 只包含事件特有数据。

P4 不把 Run 状态更新与事件写入合并为跨 Repository 的单一事务；该原子一致性由后续 Harness/Outbox 阶段处理。当前测试确保正常 Mock 流程状态与事件一致。

## 11. 前端 EventSource 封装

新增独立 SSE Client，职责：

- 使用后端返回的 `events_url` 创建 `EventSource`。
- 为 P4 支持的每个事件类型注册监听器。
- 解析并校验基础事件信封字段。
- 将事件交给 Store。
- 暴露连接状态和 `close()`。
- 网络错误时不主动关闭，让浏览器自动重连。
- 主动关闭或收到终止事件后不再重连。

相对 `events_url` 直接使用当前页面同源地址，继续通过 Vite `/api` 代理访问后端。

## 12. 前端 Store

P3 的 REST 轮询由 SSE 订阅替代。

新增状态：

```text
events
connectionStatus: idle | connecting | open | reconnecting | closed
lastSequence
seenEventIds
activeEventSource
```

处理规则：

- 创建 Run 前关闭旧连接并清理旧 Run 的事件状态。
- POST 成功后保存轻量创建响应，创建 pending assistant 消息并连接 `events_url`。
- `run.started`：将状态设为 `running`。
- `node.started`：更新 `current_node`。
- `message.delta`：将 `payload.delta` 追加到 pending assistant 消息。
- `node.completed`：保留事件，并在对应当前节点完成时清理或更新节点显示。
- `run.completed`：将状态设为 `succeeded`，用流式内容或 `payload.output` 完成 assistant 消息并关闭连接。
- `run.failed`：展示错误、结束 pending 消息并关闭连接。
- `run.cancelled`：展示取消状态并关闭连接。

去重规则：

- 已见过 `event_id` 的事件直接忽略。
- `sequence <= lastSequence` 的事件直接忽略。
- 接受事件后同时记录 `event_id` 并推进 `lastSequence`。
- 当前 P4 只允许一个活跃 Run，新 Run 会重置去重状态。

状态快照：

P4 不再为正常执行持续轮询 GET。为保持 `AgentRun` 完整字段，收到终止事件后调用一次 `GET /api/agent/runs/{run_id}`，刷新最终 tokens、cost、时间和结果。该请求失败不覆盖已经由 SSE 得到的终止状态和回复，只显示补充提示。

## 13. 页面与组件

### AgentChat

- 空状态文案更新为 P4 SSE。
- pending assistant 消息实时显示增量内容。
- 尚未收到 delta 时显示连接或运行提示。

### AgentRunPanel

- 显示 Run ID、状态、当前节点和连接状态。
- 增加按 `sequence` 排序的事件列表。
- 每项至少显示 sequence、event type、status 和时间。
- 面板仍是 P4 的轻量 Runtime 视图，不提前实现完整 DAG、Tool、Memory、Trace 或 Safety 面板。

### ChatPage

- 页面卸载时调用 Store 的 SSE 清理方法。
- 页面组件不直接创建 `EventSource`，也不直接拼接 API URL。

## 14. 错误处理

### 创建 Run 失败

- 结束 pending 状态。
- 显示现有 Axios/FastAPI 可读错误。
- 不创建 EventSource。

### SSE 建连或网络错误

- 连接状态更新为 `reconnecting`。
- 保留已接收消息、事件和 pending assistant 内容。
- 依赖原生 EventSource 自动重连。
- 不因一次 `error` 事件立即把 Run 标记为失败。

### 事件解析失败

- 忽略该条事件。
- 显示协议错误提示。
- 保持连接，让后续合法事件仍可处理。

### 终态快照 GET 失败

- 保留 SSE 得到的终态和回复。
- 显示“最终状态详情刷新失败”的非终止性提示。

### 新 Run 与卸载

- 主动关闭旧 EventSource。
- 旧连接回调通过连接 token 失效，不能覆盖新 Run。

## 15. 需要修改的文件

预计修改：

```text
backend/app/schemas/agent.py
backend/app/agent/events.py
backend/app/agent/mock_runner.py
backend/app/api/routes_agent.py
backend/app/db/models/__init__.py
backend/tests/test_agent_runs_api.py
frontend/src/api/agent.ts
frontend/src/stores/agentRun.ts
frontend/src/pages/ChatPage.vue
frontend/src/components/chat/AgentChat.vue
frontend/src/components/chat/AgentRunPanel.vue
frontend/src/styles/main.css
```

预计新增：

```text
backend/app/db/models/runtime_event.py
backend/app/db/repositories/runtime_events.py
backend/alembic/versions/20260614_0002_create_runtime_events.py
backend/tests/test_runtime_events.py
frontend/src/api/agentEvents.ts
```

具体实施计划可根据测试拆分少量辅助文件，但不改变顶层目录结构。

## 16. 接口设计

REST 路径不变：

```text
POST /api/agent/runs
GET  /api/agent/runs/{run_id}
GET  /api/agent/runs/{run_id}/events
```

`POST` 的 `events_url` 继续作为前端唯一 SSE 地址来源。页面和 Store 不自行拼接该 URL。

SSE 是 P4 唯一的运行过程增量来源；GET 只用于最终状态快照和独立详情查询。

## 17. 测试与验证

### 17.1 后端自动测试

覆盖：

- 创建事件后确实存在于 `runtime_events`。
- 同一 Run 的 sequence 从 1 连续递增。
- 不同 Run 各自从 1 开始。
- 事件信封和 payload 符合契约。
- SSE 初次连接完整回放。
- `Last-Event-ID` 只回放后续事件。
- 非法 UUID、未知事件 ID、跨 Run 事件 ID 返回 `400`。
- 未知 Run 返回 `404`。
- 终止事件发送后响应结束。
- 数据库约束拒绝非法 sequence、status 和非对象 payload。

运行：

```powershell
Set-Location backend
uv run pytest
```

### 17.2 Migration 验证

在 PostgreSQL 环境执行：

```powershell
Set-Location backend
uv run alembic upgrade head
uv run alembic downgrade 20260613_0001
uv run alembic upgrade head
```

检查 `runtime_events` 的外键、唯一约束、JSONB 和索引。

### 17.3 前端自动验证

```powershell
Set-Location frontend
pnpm build
```

必须通过 TypeScript 和 Vite 构建。

### 17.4 手动联调

1. 启动 PostgreSQL、后端和前端。
2. 打开 `/chat` 并提交消息。
3. 确认 Network 中建立 `text/event-stream` 连接。
4. 确认回复通过两个 `message.delta` 分片逐步出现。
5. 确认右侧按顺序展示六个 Mock 事件。
6. 确认 current node 和 Run status 随事件变化。
7. 确认 `run.completed` 后连接关闭并刷新最终 tokens/cost。
8. 在运行中短暂断开网络后恢复，确认浏览器重连且内容不重复。
9. 切换页面，确认 EventSource 被关闭。
10. 提交新 Run，确认旧连接和旧事件状态不会覆盖新 Run。

## 18. 风险点

- 原生 EventSource 不允许前端代码自定义 `Last-Event-ID` Header；恢复能力依赖浏览器对同一 EventSource 实例的自动重连。页面刷新后的跨实例恢复不在 P4 范围。
- 单实例 Broker 无法唤醒其他 API 实例；数据库事件不会丢失，但其他实例只能在其 SSE 心跳周期后查询到新事件。正式多实例实时广播留到 RabbitMQ 阶段。
- Run 状态更新和事件写入尚未使用统一事务或 Outbox，进程在两次提交之间崩溃可能产生短暂不一致。P4 保持 Mock 范围，后续 Harness/Outbox 解决。
- HTTP 测试客户端通常会缓冲完整流，心跳的实时等待行为主要通过较短可配置间隔或生成器级测试验证，避免测试长期挂起。

## 19. 完成标准

- `runtime_events` 通过 Model 和 Alembic Migration 创建。
- 所有 Mock Runtime 事件先持久化再通知。
- SSE 使用稳定事件信封和 UUID `id`。
- SSE 支持数据库回放、`Last-Event-ID`、心跳和终态关闭。
- 前端正常流程不再依赖 REST 短轮询。
- `message.delta` 可增量显示。
- 前端断线重连后不重复展示已处理事件。
- 页面卸载和新 Run 会关闭旧 EventSource。
- 后端测试与前端构建通过。
- 未引入 RabbitMQ、Celery 或无关依赖。
