# P3 ChatPage Mock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用 Vue 3、Pinia 和 REST 短轮询完成 Paris Agent P3 ChatPage Mock 前端闭环。

**Architecture:** `src/api/agent.ts` 负责 Agent Run 类型和 REST 调用，Pinia Store 负责单个活跃 Run、消息和轮询生命周期，页面组件只负责渲染与用户交互。开发环境通过 Vite 同源 `/api` 代理访问现有 FastAPI 后端，P3 不接入 SSE。

**Tech Stack:** Vue 3、TypeScript、Vite、Vue Router、Pinia、Axios、Element Plus、pnpm。

---

## File Map

- Create: `frontend/src/api/agent.ts`
  - Agent Run 类型、创建和查询 API。
- Create: `frontend/src/stores/agentRun.ts`
  - 消息、活跃 Run、GET 轮询、超时和清理。
- Create: `frontend/src/pages/ChatPage.vue`
  - Chat 页面组合和卸载清理。
- Create: `frontend/src/components/chat/AgentChat.vue`
- Create: `frontend/src/components/chat/ChatMessage.vue`
- Create: `frontend/src/components/chat/MessageInput.vue`
- Create: `frontend/src/components/chat/AgentRunPanel.vue`
- Modify: `frontend/src/api/http.ts`
  - 默认使用相对 `/api`。
- Modify: `frontend/vite.config.ts`
  - 配置 `/api` 开发代理。
- Modify: `frontend/.env.example`
  - 增加 API Base URL 和代理目标。
- Modify: `frontend/src/router/index.ts`
  - 新增 `/chat`。
- Modify: `frontend/src/layouts/WorkbenchLayout.vue`
  - 新增 Chat 导航、修正品牌标记和阶段标签。
- Modify: `frontend/src/styles/main.css`
  - ChatPage 响应式布局和组件样式。

### Task 1: Agent Run API 与开发代理

**Files:**
- Create: `frontend/src/api/agent.ts`
- Modify: `frontend/src/api/http.ts`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/.env.example`

- [ ] **Step 1: 定义 Agent Run 类型**

在 `agent.ts` 中定义：

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
```

同时完整定义 `AgentRunCreated` 和 `AgentRun`，字段与后端 Pydantic Schema 一致。

- [ ] **Step 2: 封装 REST API**

```typescript
export async function createAgentRun(
  payload: AgentRunCreateRequest,
): Promise<AgentRunCreated>

export async function getAgentRun(runId: string): Promise<AgentRun>
```

使用现有 `http` Axios 实例，不在组件中拼 URL。

- [ ] **Step 3: 配置同源 API**

`http.ts` 默认：

```typescript
baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api'
```

Vite：

```typescript
const proxyTarget =
  process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
```

`/api` 代理到该目标，`changeOrigin: true`。

- [ ] **Step 4: 更新环境示例**

```dotenv
VITE_API_BASE_URL=/api
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

- [ ] **Step 5: 类型构建验证**

Run:

```powershell
Set-Location frontend
pnpm build
```

Expected: TypeScript 和 Vite 构建通过。

### Task 2: Pinia Agent Run Store

**Files:**
- Create: `frontend/src/stores/agentRun.ts`

- [ ] **Step 1: 定义聊天消息和常量**

```typescript
export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  pending?: boolean
}

const POLL_INTERVAL_MS = 500
const POLL_TIMEOUT_MS = 60_000
```

- [ ] **Step 2: 定义 Store 状态**

```text
messages
currentRun
createdRun
isSubmitting
isPolling
errorMessage
pollTimer
pollStartedAt
activeRequestToken
```

`pollTimer` 保留在 Store 闭包中，不暴露为响应式业务状态。

- [ ] **Step 3: 实现消息辅助函数**

- 生成前端消息 ID。
- 添加 user 消息和 pending assistant 消息。
- 按 ID 替换 pending assistant 的内容和 pending 状态。

- [ ] **Step 4: 实现轮询**

`pollRun(runId, assistantMessageId, requestToken)`：

- 调用 GET。
- 忽略过期 request token。
- 更新 currentRun。
- 活动状态递归 `setTimeout`。
- `succeeded` 写入 final_output 或空结果提示。
- `failed`、`cancelled` 写入错误提示。
- GET 失败停止并显示状态查询失败。
- 60 秒超时停止并显示超时。

- [ ] **Step 5: 实现提交**

`submitMessage(input)`：

- trim 和 `isBusy` 二次保护。
- 停止旧轮询。
- 添加两条消息。
- POST 创建 Run。
- 保存 createdRun。
- 立即开始 GET。
- 创建失败更新 pending assistant 和错误。

- [ ] **Step 6: 实现清理**

```typescript
stopPolling()
reset()
```

`stopPolling` 清理 timer 并使旧 request token 失效。

- [ ] **Step 7: 类型构建验证**

Run:

```powershell
Set-Location frontend
pnpm build
```

Expected: Store 类型检查通过。

### Task 3: Chat 组件

**Files:**
- Create: `frontend/src/components/chat/ChatMessage.vue`
- Create: `frontend/src/components/chat/AgentChat.vue`
- Create: `frontend/src/components/chat/MessageInput.vue`
- Create: `frontend/src/components/chat/AgentRunPanel.vue`

- [ ] **Step 1: 实现 ChatMessage**

- Props 使用 `ChatMessageItem`。
- role 映射为“你”“Paris Agent”“系统”。
- pending 时显示等待标记。
- 使用 `white-space: pre-wrap`，不使用 `v-html`。

- [ ] **Step 2: 实现 AgentChat**

- Props 接收消息数组。
- 空状态展示使用说明。
- 使用 `watch` 和 `nextTick` 滚动到底部。
- 不直接访问 Store。

- [ ] **Step 3: 实现 MessageInput**

- Props: `disabled`。
- Emits: `submit(message: string)`。
- Enter 提交、Shift+Enter 换行。
- trim 空输入不触发。
- 提交成功触发后清空本地输入。

- [ ] **Step 4: 实现 AgentRunPanel**

- Props: `run`、`createdRun`、`errorMessage`。
- 显示 Run ID、status、current_node 和时间。
- 无 Run 时显示等待提示。
- 不显示 events 列表。

- [ ] **Step 5: 类型构建验证**

Run:

```powershell
Set-Location frontend
pnpm build
```

Expected: 四个组件编译通过。

### Task 4: ChatPage、路由与布局

**Files:**
- Create: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/WorkbenchLayout.vue`

- [ ] **Step 1: 实现 ChatPage**

- 使用 `storeToRefs` 获取 Store 状态。
- 组合 AgentChat、MessageInput 和 AgentRunPanel。
- MessageInput 调用 `submitMessage`。
- `onBeforeUnmount(stopPolling)`。

- [ ] **Step 2: 新增路由**

```typescript
{
  path: 'chat',
  name: 'chat',
  component: ChatPage,
  meta: { title: 'Chat' },
}
```

保留 `/dashboard` 和根路径重定向。

- [ ] **Step 3: 更新 WorkbenchLayout**

- 品牌标记 `AGI` 改为 `PA`。
- 新增 `/chat` 导航。
- 阶段标签改为 `P3 / ChatPage Mock`。
- 顶部 Tag 在 Chat 页面显示 `P3 Integration`，Dashboard 保持 Foundation。

- [ ] **Step 4: 类型构建验证**

Run:

```powershell
Set-Location frontend
pnpm build
```

Expected: 路由和页面编译通过。

### Task 5: 样式与手动联调

**Files:**
- Modify: `frontend/src/styles/main.css`

- [ ] **Step 1: 添加 ChatPage 桌面布局**

实现：

```text
.chat-page
.chat-workspace
.chat-column
.run-panel
.message-list
.message-row
.message-input
```

延续现有背景、边框和颜色变量，不引入渐变或新字体。

- [ ] **Step 2: 添加响应式布局**

- 1100px 以下 Chat 与 Run Panel 上下排列。
- 640px 以下减小 workspace padding。
- 输入按钮在窄屏保持可点击。

- [ ] **Step 3: 构建验证**

Run:

```powershell
Set-Location frontend
pnpm build
```

Expected: 构建退出码 0。

- [ ] **Step 4: 后端测试**

Run:

```powershell
Set-Location backend
uv run pytest
```

Expected: 现有测试全部通过。

- [ ] **Step 5: 联调验证**

启动：

```powershell
Set-Location backend
uv run uvicorn app.main:app --reload

Set-Location ..\frontend
pnpm dev
```

验证：

```text
/dashboard 仍可访问
/chat 可访问
空输入不能提交
提交后显示 run_id
状态最终为 succeeded
显示模拟回复
运行期间不能重复提交
切换页面停止旧轮询
关闭后端后显示连接错误
```

- [ ] **Step 6: 检查改动范围**

Run:

```powershell
git diff --check
git status --short
```

Expected: P3 只修改计划列出的前端文件和计划文档；不覆盖现有后端改动。
