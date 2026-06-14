# Agent Run Mock Contract

## 1. 文档状态

该文件创建时使用了早期阶段名 `P1`，因此保留文件名以避免已有链接失效。

根据当前 `AGENTS.md`：

```text
P2：Agent Run mock
P3：ChatPage mock
P4：SSE 事件流
```

本文记录已经实现的 P2 后端 Agent Run Mock 契约，以及 P4 之前临时使用的进程内 SSE
行为。后续需求编号必须以 `AGENTS.md` 为准。

权威来源：

```text
backend/app/db/models/agent_run.py
backend/app/schemas/agent.py
backend/app/api/routes_agent.py
backend/app/agent/events.py
backend/app/agent/mock_runner.py
backend/alembic/versions/
```

---

## 2. 实现范围

当前闭环：

```text
创建 Run
↓
持久化 queued 状态
↓
启动 FastAPI 进程内 Mock Runner
↓
更新 running 状态
↓
发送 mock SSE 事件
↓
更新 succeeded 或 failed
↓
通过 GET 查询最终状态
```

当前不包含：

```text
Skill Registry
LangGraph
DAG Runtime
长期记忆
RAG
Tool Manager
RabbitMQ / Celery
Docker Sandbox
持久化 Runtime Event
多实例事件广播
```

---

## 3. Agent Run 数据契约

### 3.1 字段

| 字段 | 类型 | 必填 | 当前说明 |
| --- | --- | --- | --- |
| run_id | UUID | 是 | 对外业务标识，唯一 |
| thread_id | UUID/null | 否 | P2 尚未实现会话管理 |
| user_id | UUID | 是 | 当前来自 `DEFAULT_USER_ID` |
| project_id | UUID/null | 否 | P2 尚未实现项目管理 |
| skill_id | string/null | 否 | P5 Skill Registry 前通常为空 |
| task_type | string | 是 | 默认 `chat` |
| status | AgentRunStatus | 是 | 默认 `queued` |
| current_node | string/null | 否 | 当前执行节点，终态时为空 |
| input | string | 是 | 去除首尾空白后不能为空 |
| final_output | string/null | 否 | 成功时的最终输出 |
| error_message | string/null | 否 | 失败时的错误信息 |
| total_tokens | integer | 是 | 非负，默认 0 |
| total_cost | decimal string | 是 | 非负，固定 8 位小数 |
| created_at | RFC 3339 datetime | 是 | 带时区 |
| updated_at | RFC 3339 datetime | 是 | 带时区 |

### 3.2 状态

允许值：

```text
queued
running
succeeded
failed
cancelled
waiting_approval
```

禁止使用 `success` 作为 Agent Run 状态。

P2 Mock Runner 实际使用：

```text
queued -> running -> succeeded
queued -> running -> failed
```

`cancelled` 和 `waiting_approval` 为后续阶段预留，P2 尚未提供触发接口。

---

## 4. 创建 Agent Run

### 4.1 请求

```http
POST /api/agent/runs
Content-Type: application/json
```

```json
{
  "thread_id": null,
  "project_id": null,
  "skill_id": null,
  "task_type": "chat",
  "input": "Kafka 为什么能够保证高吞吐？"
}
```

校验：

- `thread_id` 和 `project_id` 必须是 UUID 或 null。
- `skill_id` 最大长度 128。
- `task_type` 长度为 1-64，默认 `chat`。
- `input` 必填，trim 后不能为空。
- 客户端不能提交 `user_id`、`run_id`、`status`、成本或时间字段。

### 4.2 响应

```http
HTTP/1.1 202 Accepted
Location: /api/agent/runs/{run_id}
```

```json
{
  "run_id": "11111111-1111-4111-8111-111111111111",
  "status": "queued",
  "created_at": "2026-06-14T00:00:00Z",
  "detail_url": "/api/agent/runs/11111111-1111-4111-8111-111111111111",
  "events_url": "/api/agent/runs/11111111-1111-4111-8111-111111111111/events"
}
```

语义：

- 返回 `202 Accepted`，不等待 Mock Runner 完成。
- 数据库提交成功后才启动后台任务。
- `Location` 与 `detail_url` 指向同一资源。
- `user_id` 当前由后端配置提供；接入认证后改为认证上下文。

---

## 5. 查询 Agent Run

### 5.1 请求

```http
GET /api/agent/runs/{run_id}
```

`run_id` 必须是 UUID。

### 5.2 响应

```json
{
  "run_id": "11111111-1111-4111-8111-111111111111",
  "thread_id": null,
  "user_id": "00000000-0000-0000-0000-000000000001",
  "project_id": null,
  "skill_id": null,
  "task_type": "chat",
  "status": "succeeded",
  "current_node": null,
  "input": "Kafka 为什么能够保证高吞吐？",
  "final_output": "这是 Paris Agent 的模拟回复。",
  "error_message": null,
  "total_tokens": 32,
  "total_cost": "0.00000000",
  "created_at": "2026-06-14T00:00:00Z",
  "updated_at": "2026-06-14T00:00:01Z"
}
```

当前错误行为：

- 合法但不存在的 UUID 返回 `404`，detail 为 `Agent run not found`。
- 非 UUID 路径参数由 FastAPI 返回 `422`。
- 统一 Problem Details 将在 API 错误规范专项任务中引入，不能在前端假定已存在。

---

## 6. Mock SSE 契约

### 6.1 请求

```http
GET /api/agent/runs/{run_id}/events
Accept: text/event-stream
```

不存在的 Run 返回 `404`。

### 6.2 当前事件类型

```text
run.started
node.started
message.delta
node.completed
run.completed
run.failed
```

P2 成功路径事件顺序：

```text
run.started
node.started
message.delta
message.delta
node.completed
run.completed
```

### 6.3 当前事件字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| event_type | string | 事件类型 |
| run_id | UUID | 所属 Run |
| sequence | integer | 当前进程内从 1 递增 |
| timestamp | datetime | UTC 时间 |
| status | AgentRunStatus | 事件发生时 Run 状态 |
| node_name | string/null | 节点类事件使用 |
| delta | string/null | `message.delta` 使用 |
| output | string/null | 完成事件使用 |
| error_message | string/null | 失败事件使用 |

### 6.4 SSE 帧

```text
id: 1
event: run.started
data: {"event_type":"run.started","run_id":"11111111-1111-4111-8111-111111111111","sequence":1,"timestamp":"2026-06-14T00:00:00Z","status":"running","node_name":"mock_executor","delta":null,"output":null,"error_message":null}

```

后端使用命名事件，前端必须通过 `addEventListener(eventType, handler)` 监听；不能只依赖
`EventSource.onmessage`。

### 6.5 终止规则

当前终止事件：

```text
run.completed
run.failed
```

Broker 发送终止事件后结束该连接的异步迭代。

---

## 7. P2 临时限制

当前事件 Broker 只适用于最小闭环：

- 事件只保存在 API 进程内存。
- API 重启后事件丢失。
- 多实例之间不共享历史或通知。
- 当前 `sequence` 由内存列表长度生成。
- 当前不处理 `Last-Event-ID`。
- 当前没有心跳。
- 客户端在 Runner 已完成后连接时，只能回放同一进程仍保留的历史。

前端联调必须把这些限制视为开发期行为，不能将其当作生产保证。

---

## 8. P4 兼容演进

P4 引入 `runtime_events` 时，目标稳定信封为：

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

迁移要求：

1. `UNIQUE (run_id, sequence)`。
2. 事件先持久化，再通知 SSE 订阅者。
3. SSE `id` 可用于 `Last-Event-ID` 回放。
4. 增加心跳和客户端去重。
5. 增加 `run.cancelled` 终止事件。
6. P3 前端与 P4 后端必须在同一专项任务中确认兼容方式。
7. 不能无版本或无兼容映射地直接删除 P2 扁平字段。

---

## 9. 验证命令

后端：

```powershell
Set-Location backend
uv run alembic upgrade head
uv run pytest
uv run uvicorn app.main:app --reload
```

手动验证：

1. 调用 `POST /api/agent/runs`，确认返回 `202` 和 `Location`。
2. 使用返回的 `run_id` 连接 `/events`。
3. 确认收到命名 SSE 事件和两段 `message.delta`。
4. 调用 GET，确认最终状态为 `succeeded`。
5. 确认 `final_output` 为模拟回复、`current_node` 为 null。
6. 使用不存在 UUID 验证 GET 和 SSE 返回 `404`。
