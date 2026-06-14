# P3 ChatPage Mock 设计规格

## 1. 目标

P3 完成 Paris Agent 前端聊天页与现有 P2 Agent Run REST API 的最小联调闭环：

```text
用户输入一句话
↓
前端创建 Agent Run
↓
后端持久化并执行 Mock Runner
↓
前端通过 GET 短轮询 Run 状态
↓
前端展示模拟回复和运行状态
```

本阶段只实现 ChatPage Mock，不实现 P4 的 SSE 前端订阅和持久化事件能力。

## 2. 范围

### 2.1 本次实现

- 新增 `/chat` 路由和侧栏导航入口。
- 保留现有 Dashboard 和 Workbench 视觉风格。
- 创建 ChatPage、AgentChat、ChatMessage、MessageInput、AgentRunPanel。
- 创建 `frontend/src/api/agent.ts`。
- 创建 `useAgentRunStore`。
- 调用 `POST /api/agent/runs` 创建 Run。
- 使用 `GET /api/agent/runs/{run_id}` 短轮询状态。
- 展示用户消息、等待状态、模拟回复、Run ID、状态和当前节点。
- 展示请求失败、Run 失败、取消和轮询超时。
- 页面卸载或开始新 Run 时清理旧轮询。
- 更新 `.env.example` 和 Vite 开发代理配置。

### 2.2 明确不做

- 不使用 `GET /api/agent/runs/{run_id}/events`。
- 不创建 EventSource 封装。
- 不展示 SSE events 列表。
- 不实现 `message.delta` 流式文本。
- 不实现断线恢复、心跳、事件去重和 `Last-Event-ID`。
- 不创建 `runtime_events` 表或 Migration。
- 不实现会话历史、项目、Skill、RAG、长期记忆、工具、DAG 或 Sandbox。
- 不修改后端接口或 CORS。
- 不新增前端依赖。

## 3. 设计选择

采用 Pinia 管理单个活跃 Run，并使用 `setTimeout` 驱动 GET 短轮询。

不在 P3 使用 TanStack Query 轮询，原因是：

- 当前只存在一个活跃 Run。
- 消息状态和 Run 状态需要一起更新。
- P4 会将状态更新来源替换为 SSE。
- 避免同时在 Pinia 和 Query Cache 中保存相同的活跃 Run。

不在页面组件中直接管理轮询，避免计时器、API 和消息更新耦合到视图。

## 4. 页面结构

现有 `WorkbenchLayout` 继续负责全局左侧栏和顶部栏。

```text
WorkbenchLayout
├── Sidebar
│   ├── Paris Agent
│   ├── Dashboard
│   └── Chat
└── Workspace
    └── ChatPage
        ├── AgentChat
        │   └── ChatMessage[]
        ├── MessageInput
        └── AgentRunPanel
```

ChatPage 主体使用两栏：

```text
聊天区：minmax(0, 1fr)
运行面板：约 320px
```

窄屏时运行面板移动到聊天区下方。

## 5. 文件职责

### 5.1 `frontend/src/api/agent.ts`

负责：

- Agent Run TypeScript 类型。
- `createAgentRun(payload)`。
- `getAgentRun(runId)`。

该文件不维护 Vue 响应式状态和轮询计时器。

### 5.2 `frontend/src/stores/agentRun.ts`

负责：

- 聊天消息。
- 当前 Agent Run。
- 提交中和轮询中状态。
- 错误信息。
- 创建 Run。
- GET 轮询。
- 终态处理。
- 轮询取消和 Store 重置。

Store 只允许一个活跃 Run。新提交前必须停止旧轮询。

### 5.3 `frontend/src/pages/ChatPage.vue`

负责组合组件、调用 Store Action，并在组件卸载时停止轮询。

页面不直接发送 HTTP 请求。

### 5.4 组件

`AgentChat.vue`

- 展示消息列表。
- 无消息时展示 P3 引导文案。
- 消息变化时滚动到底部。

`ChatMessage.vue`

- 展示 user、assistant 和 system 三类消息。
- 等待消息展示轻量加载状态。
- 不解析 Markdown。

`MessageInput.vue`

- 管理输入框本地文本。
- trim 后为空时禁止提交。
- 正在提交或运行时禁止重复提交。
- Enter 提交，Shift+Enter 换行。

`AgentRunPanel.vue`

- 展示 run_id。
- 展示 status。
- 展示 current_node。
- 展示 created_at、updated_at。
- 展示错误或空状态。
- P3 不展示事件列表。

## 6. 类型设计

```typescript
export type AgentRunStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'waiting_approval'

export interface AgentRunCreateRequest {
  thread_id?: string | null
  project_id?: string | null
  skill_id?: string | null
  task_type?: string
  input: string
}

export interface AgentRunCreated {
  run_id: string
  status: AgentRunStatus
  created_at: string
  detail_url: string
  events_url: string
}

export interface AgentRun {
  run_id: string
  thread_id: string | null
  user_id: string
  project_id: string | null
  skill_id: string | null
  task_type: string
  status: AgentRunStatus
  current_node: string | null
  input: string
  final_output: string | null
  error_message: string | null
  total_tokens: number
  total_cost: string
  created_at: string
  updated_at: string
}
```

聊天消息：

```typescript
export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  pending?: boolean
}
```

消息 ID 只用于前端渲染，不写入后端。

## 7. 数据流

### 7.1 提交流程

1. MessageInput trim 用户输入。
2. Store 停止旧轮询并清理当前错误。
3. 添加 user 消息。
4. 添加 pending assistant 消息。
5. 调用 `createAgentRun`。
6. 保存轻量创建响应。
7. 立即调用一次 `getAgentRun`。
8. 非终态时安排下一次轮询。

### 7.2 轮询流程

```text
GET Run
↓
更新 currentRun
↓
queued/running/waiting_approval
  等待 500ms 后再次 GET
↓
succeeded
  使用 final_output 更新 pending assistant 消息
  停止轮询
↓
failed/cancelled
  更新 pending assistant 消息为错误说明
  停止轮询
```

轮询使用递归 `setTimeout`，不使用 `setInterval`，避免前一次请求未结束时发起重叠请求。

### 7.3 超时

- 轮询总时长上限为 60 秒。
- 超时后停止轮询。
- 保留当前 Run 状态。
- pending assistant 消息改为“运行状态查询超时，请稍后查看。”
- Store 写入可见错误信息。

## 8. 状态和终态

活动状态：

```text
queued
running
waiting_approval
```

终态：

```text
succeeded
failed
cancelled
```

`waiting_approval` 在 P3 只展示，不提供审批操作。

`succeeded` 但 `final_output` 为空时，显示明确的空结果提示，不能让 pending 状态永久存在。

## 9. 错误处理

### 9.1 创建失败

- 停止 loading。
- pending assistant 消息改为连接失败提示。
- 显示 Axios/FastAPI 可读错误。
- 不启动轮询。

### 9.2 轮询请求失败

P3 不做无限重试：

- 单次 GET 失败后停止轮询。
- 保留 run_id 和最近状态。
- pending assistant 消息改为状态查询失败提示。
- 用户可以重新提交新 Run。

### 9.3 重复提交

当 `isBusy` 为 true 时 MessageInput 禁用。Store Action 仍进行二次保护，防止组件层被
绕过。

## 10. API 地址与开发代理

浏览器统一请求相对路径 `/api`。

`frontend/src/api/http.ts`：

```text
baseURL = VITE_API_BASE_URL，默认 /api
```

`.env.example`：

```text
VITE_API_BASE_URL=/api
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

Vite 将 `/api` 转发到 `VITE_API_PROXY_TARGET`。生产环境由反向代理提供同源 `/api`。

## 11. 视觉规则

- 延续当前深色 Workbench 样式和边框语言。
- 不新增 UI 库和字体。
- 不重做 Dashboard。
- ChatPage 视觉重点是可读性和运行状态，不加入复杂动画。
- 侧栏品牌标记从遗留 `AGI` 改为 `PA`。
- 阶段标签更新为 `P3 / ChatPage Mock`。

## 12. 验证

### 12.1 自动验证

```powershell
Set-Location frontend
pnpm build
```

必须通过 TypeScript 和 Vite 构建。

### 12.2 手动联调

1. 启动 PostgreSQL。
2. 启动后端。
3. 启动前端。
4. 打开 `/chat`。
5. 输入非空消息。
6. 确认 POST 返回后显示 run_id。
7. 确认状态经过 queued/running 并最终 succeeded。
8. 确认模拟回复替换等待消息。
9. 确认右侧展示 current_node 和时间。
10. 确认提交期间不能重复提交。
11. 关闭后端后提交，确认显示连接错误。
12. 切换页面，确认旧轮询停止。

### 12.3 完成标准

- `/dashboard` 保持可用。
- `/chat` 页面可用。
- 页面组件不直接写 API URL。
- Store 只维护一个活跃 Run。
- P3 使用 REST 短轮询，不使用 SSE。
- 成功、失败、取消、超时和连接错误均能结束 pending 状态。
- `pnpm build` 通过。
- 未修改后端代码和数据库。
