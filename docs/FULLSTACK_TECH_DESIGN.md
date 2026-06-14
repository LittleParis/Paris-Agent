# Paris Agent 前后端一体化技术设计

## 1. 文档说明

### 1.1 文档用途

本文是 Paris Agent 的总体技术设计基线，用于约束跨阶段架构、模块职责、数据契约、
接口规范、可靠性要求和 P0-P16 实现顺序。

本文不替代专项契约、SQLAlchemy Model、Alembic Migration、Pydantic Schema 或
OpenAPI。进入具体阶段前，必须先编写或确认对应专项契约。

### 1.2 权威层级

发生冲突时按以下顺序处理：

1. `AGENTS.md`：项目定位、技术栈、目录规范、开发流程和 P0-P16 阶段顺序。
2. `docs/FULLSTACK_TECH_DESIGN.md`：总体架构和跨阶段统一契约。
3. 专项契约文档：某个阶段或领域的详细设计。
4. 已实现的 Model、Migration、Schema、OpenAPI 和自动化测试：当前运行事实。

如果专项文档与已实现代码冲突，先判断实现是否符合前两层约束。实现正确则更新文档；
实现错误则单独创建修复任务，禁止用修改文档掩盖实现缺陷。

### 1.3 状态标记

```text
[已实现] 已经存在代码、配置或 Migration，并完成基础验证
[进行中] 当前阶段正在实现，契约允许小范围调整
[目标设计] 已确定方向，但尚未实现
[阶段外] 当前阶段明确不实现
```

未来能力必须标为 `[目标设计]` 或 `[阶段外]`，不能描述成当前已经可用。

---

## 2. 项目定位

### 2.1 项目名称

```text
Paris Agent
```

Paris Agent 是面向程序员技术学习场景的 Skill-based Agent Workbench，不是普通聊天
机器人。

### 2.2 核心目标

```text
Skill-based Agent Workflow
自研长期记忆系统
Hybrid GraphRAG
动态图 ReAct Runtime
Agent Harness 容错执行引擎
多层安全校验与 Docker Sandbox
RabbitMQ 异步任务队列
Agent Runtime 前端可视化
RAG 评测与可观测性
```

### 2.3 目标业务场景

- 技术问答与来源引用。
- 个性化学习路线。
- 项目和技术文档知识库。
- 长期学习画像与项目记忆。
- Skill 显式调用和自动路由。
- 工具审批与安全执行。
- Agent Run、节点、工具、Checkpoint 和 Trace 可视化。
- RAG 检索与生成质量评测。

### 2.4 当前非目标

- 不在早期阶段拆分微服务。
- 不一次性接入全部中间件。
- 不让 Skill、Agent 或页面绕过 Tool Manager 直接调用高风险工具。
- 不把聊天记录直接等同于长期记忆。
- 不在没有专项设计和 Migration 的情况下批量创建所有未来表。

---

## 3. 当前实现基线

### 3.1 阶段状态

| 阶段 | 状态 | 当前说明 |
| --- | --- | --- |
| P0 项目骨架 | 已实现 | backend、frontend、docker、docs、scripts 已建立 |
| P1 health check + 基础布局 | 已实现 | FastAPI health check、Vue Dashboard 和 WorkbenchLayout 已存在 |
| P2 Agent Run mock | 已实现 | 数据库持久化、POST/GET、进程内 Mock Runner 已存在 |
| P3 ChatPage mock | 已实现 | ChatPage、组件、Pinia、REST API Client 和短轮询已完成 |
| P4 SSE 事件流 | 部分实现 | 后端进程内 SSE 已实现，持久化、重连和前端订阅尚未完成 |
| P5-P16 | 未开始 | 只能按阶段专项实现 |

早期文档曾把 Agent Run Mock 称为“P1”。该叫法只保留在历史文件名
`P1_AGENT_RUN_CONTRACT.md` 中；后续需求编号统一以 `AGENTS.md` 为准。

### 3.2 已实现 Agent Run API

```http
POST /api/agent/runs
GET /api/agent/runs/{run_id}
GET /api/agent/runs/{run_id}/events
```

当前实现限制：

- Runner 使用 FastAPI 进程内异步任务，不是 Celery、LangGraph 或生产 Harness。
- SSE 事件保存在进程内存中，服务重启后丢失。
- 不支持多 API 实例共享事件。
- 不支持持久化回放和 `Last-Event-ID` 断线恢复。
- P2 不包含 Skill、RAG、记忆、工具和 Sandbox。

---

## 4. 技术栈与依赖管理

### 4.1 后端

```text
Python 3.11+
FastAPI
Pydantic / pydantic-settings
SQLAlchemy
Alembic
PostgreSQL
Redis
RabbitMQ
Celery
LangGraph
Milvus
Elasticsearch
Neo4j
Docker Sandbox
OpenTelemetry
Prometheus
Grafana
RAGAS
```

依赖管理固定使用：

```powershell
uv add package_name
uv add --dev package_name
uv sync
uv run uvicorn app.main:app --reload
```

禁止将 `requirements.txt`、`pip install` 或 `pip freeze` 作为主依赖流程。

### 4.2 前端

```text
Vue 3
TypeScript
Vite
Vue Router
Pinia
Axios
Element Plus
TanStack Query for Vue
ECharts
Monaco Editor
SSE / WebSocket
```

依赖管理固定使用：

```powershell
pnpm add package_name
pnpm add -D package_name
pnpm install
pnpm dev
```

项目只使用 pnpm，不混用 npm 和 yarn。

### 4.3 中间件阶段

```text
第一阶段：PostgreSQL、Redis、RabbitMQ
第二阶段：Milvus、Elasticsearch、Neo4j
第三阶段：Prometheus、Grafana、OpenTelemetry Collector
```

所有秘密和环境差异通过 `.env` 注入，仓库只提交 `.env.example`。

---

## 5. 系统架构

### 5.1 总体结构

```text
Vue 3 Workbench
  ├── REST API Client
  ├── SSE Client
  └── Runtime Visualization
            ↓
FastAPI Delivery Layer
            ↓
Application Use Cases
            ↓
Skill / Runtime / Memory / RAG / Tool Domain Policies
            ↓
Repository / Queue / Model / Tool Ports
            ↓
Infrastructure Adapters
  ├── PostgreSQL
  ├── Redis
  ├── RabbitMQ / Celery
  ├── Milvus
  ├── Elasticsearch
  ├── Neo4j
  └── Docker Sandbox
```

### 5.2 架构形态

后端采用模块化单体。早期阶段不拆微服务，但模块必须通过明确接口通信，避免路由、
ORM Model 和基础设施代码相互穿透。

依赖方向：

```text
API / Queue Consumer
        ↓
Application Use Case
        ↓
Domain Policy / Runtime Contract
        ↓
Port
        ↓
Infrastructure Adapter
```

FastAPI 路由只负责：

1. 解析和验证协议输入。
2. 注入认证、Session 和应用服务。
3. 调用 Use Case。
4. 映射 HTTP 响应和错误。

复杂业务流程不能长期堆积在路由、Pydantic Schema 或 SQLAlchemy Model 中。

### 5.3 后端模块职责

```text
api             HTTP 和 SSE 路由
core            配置、日志、异常和通用安全
db              Session、Model、Repository 和数据库适配
schemas         HTTP、消息和公开数据结构
agent           AgentState、LangGraph、DAG Runtime 和 Harness
skills          Skill Registry、Router、Validator 和 Executor
memory          长期记忆写入、合并、检索和策略
rag             文档处理、Dense、BM25、Graph 和融合检索
tools           Tool Registry、Manager、Executor 和适配器
security        输入、输出、工具风险、权限和审批
queue           Celery、消息 Schema、Producer 和 Consumer
eval            Golden Query、检索评测和生成评测
observability   Trace、Metric、Log 和 Cost
```

---

## 6. 核心执行流程

### 6.1 完整目标流程

```text
用户输入
↓
Input Guardrail
↓
Skill Router
↓
Memory Retriever
↓
Hybrid Retriever
↓
Planner
↓
DAG ReAct Runtime
↓
Tool Manager
↓
Verifier
↓
Output Guardrail
↓
Memory Writer
↓
最终响应
```

该流程属于 `[目标设计]`。每个阶段只接入当期所需节点，不能在 P2-P4 假装已经具备
完整 Runtime。

### 6.2 运行时职责边界

#### LangGraph

- 表达高层状态图。
- 提供暂停、恢复和人工审批入口。
- 对接 Checkpoint 持久化。
- 不重复实现底层工具安全和数据库 Repository。

#### 自研 DAG Runtime

- 校验 DAG 结构和节点 Schema。
- 检测环、缺失依赖和非法节点。
- 进行拓扑调度和可控并行执行。
- 把节点执行委托给受 Harness 管理的 Executor。

#### Agent Harness

- 管理 Run 生命周期和合法状态迁移。
- 管理超时、重试、Fallback、取消和恢复。
- 记录事件、Trace、Checkpoint 和成本。
- 强制工具隔离和安全策略。

#### Skill Executor

- 加载经过版本校验的 Skill。
- 校验输入和输出 Schema。
- 将 Skill Workflow 转换为 DAG Plan。
- 不直接执行外部工具。

#### Tool Manager

- 所有工具调用的唯一入口。
- 执行权限、风险、审批和参数校验。
- 调用具体 Tool Adapter。
- 写入工具调用和审计事件。

### 6.3 AgentState 原则

AgentState 是运行态数据契约，不直接等同数据库表。大型历史列表不无限累积在单一
State 中，事件、节点、工具调用和 Checkpoint 应持久化到各自存储。

最低字段：

```text
run_id
thread_id
user_id
project_id
skill_id
skill_version
input
messages
current_node
node_states
retrieval_context
tool_results
final_output
error
usage
metadata
```

---

## 7. Skill 系统

### 7.1 Skill 定义

Skill 是版本化能力包，至少包含：

```text
skill_id
name
description
version
input_schema
output_schema
prompt
tools
workflow
memory_policy
safety_policy
runtime_config
```

Skill 定义使用 YAML，位于：

```text
backend/app/skills/definitions/
```

### 7.2 第一批 Skill

```text
tech_qa
learning_path
document_ingest
rag_eval
memory_consolidation
code_sandbox
project_summary
codex_task
```

### 7.3 版本规则

- `skill_id` 标识逻辑能力。
- `version` 使用语义化版本。
- 已被 Run 引用的 Skill Version 不可原地修改。
- `agent_skill_runs` 必须记录实际执行版本。
- YAML 是源码，数据库保存可查询的发布元数据和不可变配置快照。

---

## 8. 长期记忆

### 8.1 记忆类型

```text
short_term
learning_profile
semantic
episodic
project
procedural
task
runtime
```

### 8.2 写入流程

```text
候选内容
↓
Memory Extractor
↓
Memory Classifier
↓
Importance / Confidence Scorer
↓
敏感信息与安全检查
↓
Embedding
↓
Similarity Search
↓
Deduplication
↓
Merge / Create / Reject
↓
PostgreSQL + Milvus
```

记忆写入必须有来源、归属用户、可选项目、版本、置信度和删除策略。

### 8.3 检索评分

初始评分可以采用：

```text
similarity * 0.45
+ importance * 0.25
+ recency * 0.15
+ access_weight * 0.10
+ project_relevance * 0.05
```

权重是可配置实验参数，不作为永久硬编码。进入评测阶段后通过数据调整。

---

## 9. RAG 与数据所有权

### 9.1 分阶段检索

```text
基础 RAG：Milvus Dense Retrieval
Hybrid RAG：Milvus + Elasticsearch BM25 + RRF
GraphRAG：Hybrid Retrieval + Neo4j Graph Retrieval
```

### 9.2 数据所有权

| 系统 | 数据职责 |
| --- | --- |
| PostgreSQL | 业务事实、状态、关系、版本、审计、外部索引同步状态 |
| Redis | 缓存、限流、短期锁和可丢失临时状态 |
| RabbitMQ | 消息传递，不作为长期事实存储 |
| Milvus | Embedding 向量和向量索引 |
| Elasticsearch | Chunk 文本的稀疏检索索引 |
| Neo4j | 知识实体、关系和图检索投影 |

Milvus、Elasticsearch 和 Neo4j 都是可由 PostgreSQL 元数据和原始文档重建的投影。

PostgreSQL 至少记录：

```text
external_id
sync_status
index_version
last_synced_at
sync_error
```

### 9.3 Hybrid Retrieval

```text
Query Normalization
↓
可选 Query Rewrite
↓
Dense / BM25 / Graph 并行召回
↓
RRF 融合
↓
可选 Rerank
↓
Context Builder
↓
Answer + Sources
```

初始 RRF 参数可使用 `k=60`，但所有 top-k 和权重必须可配置并通过评测验证。

---

## 10. Tool Registry 与安全

### 10.1 工具元数据

```text
name
description
input_schema
output_schema
risk_level
requires_approval
enabled
timeout_seconds
```

风险等级：

```text
safe
low
medium
high
block
```

### 10.2 工具执行链

```text
Tool Manager
↓
Schema Validator
↓
Tool Guardrail
↓
Permission Checker
↓
Approval Manager
↓
Tool Executor / Sandbox
↓
Output Validator
↓
Audit Logger
```

### 10.3 Docker Sandbox 最低要求

```text
非 root 用户
镜像白名单与固定 digest
network none
read-only root filesystem
cap-drop ALL
no-new-privileges
seccomp / AppArmor
内存、CPU、PID、磁盘和时间限制
stdout / stderr 大小限制
临时目录隔离与回收
并发限制
```

命令黑名单只能作为补充，不能替代容器隔离、权限最小化和资源限制。

---

## 11. RabbitMQ 与 Celery

### 11.1 Exchange 与队列

```text
Exchange: paris.agent.events
Type: topic
```

```text
document.ingest.queue
document.embedding.queue
agent.run.events.queue
tool.audit.logs.queue
rag.eval.tasks.queue
cost.usage.events.queue
sandbox.exec.queue
```

### 11.2 消息信封

所有业务消息至少包含：

```json
{
  "message_id": "UUID",
  "message_type": "document.ingest.requested",
  "schema_version": 1,
  "occurred_at": "2026-06-14T00:00:00Z",
  "correlation_id": "UUID",
  "causation_id": "UUID-or-null",
  "idempotency_key": "stable-business-key",
  "payload": {}
}
```

### 11.3 可靠性规则

- Producer 的数据库变更与待发送消息通过 Transactional Outbox 保证一致。
- Consumer 提交本地数据库事务后才 ACK。
- 消费者必须按 `message_id` 或业务幂等键去重。
- 可重试错误使用指数退避和最大重试次数。
- 不可重试错误或超过重试上限的消息进入 DLQ。
- 日志和 Trace 必须携带 `correlation_id`。
- 消息 Schema 通过 `schema_version` 演进，禁止静默破坏消费者。

---

## 12. 数据库统一规范

### 12.1 类型规范

```text
内部主键：BIGINT GENERATED ALWAYS AS IDENTITY
外部业务标识：UUID
字符串：TEXT，必要时使用长度 CHECK
时间：TIMESTAMPTZ
金额/成本：NUMERIC(18,8)
计数：INTEGER 或 BIGINT，并增加非负 CHECK
可扩展载荷：JSONB，并增加对象/数组类型 CHECK
```

禁止新设计使用：

```text
BIGSERIAL
无时区 TIMESTAMP
FLOAT 保存金额
用 VARCHAR(n) 代替业务长度约束
无理由的 PostgreSQL ENUM
```

### 12.2 基础领域表

| 领域 | 表 | 引入阶段 |
| --- | --- | --- |
| Identity | users | 认证与多用户专项阶段 |
| Project | projects、project_members | 项目上下文阶段 |
| Conversation | chat_threads、chat_messages | Chat 持久化阶段 |
| Runtime | agent_runs | P2，已实现 |
| Runtime | runtime_events | P4 |
| Runtime | agent_node_states、agent_tool_calls、agent_checkpoints | P10-P11 |
| Skill | agent_skills、agent_skill_versions、agent_skill_runs | P5 |
| Memory | agent_memories | P6 |
| Knowledge | documents、document_chunks | P7 |
| Audit | audit_logs | P9-P12 |
| Evaluation | rag_eval_tasks、rag_eval_results | P15 |

`agent_steps` 不是默认必建表。只有定义其与 `agent_node_states` 的非重复用途后才能创建。

### 12.3 约束与索引

每张表必须明确：

- 业务必填字段和默认值。
- 状态、范围和非空白 CHECK。
- 业务唯一约束。
- 外键和 `ON DELETE` 策略。
- 每个高频外键的显式索引。
- API 查询所需组合索引。
- 数据保留、归档和删除规则。

推荐访问路径：

```text
agent_runs (user_id, created_at DESC)
agent_runs (thread_id, created_at DESC)
agent_runs (project_id, created_at DESC)
agent_runs active partial index (status, created_at)
runtime_events UNIQUE (run_id, sequence)
runtime_events (run_id, sequence)
agent_node_states UNIQUE (run_id, node_id)
agent_tool_calls (run_id, created_at)
agent_checkpoints (run_id, created_at DESC)
agent_memories (user_id, memory_type, updated_at DESC)
documents (user_id, created_at DESC)
document_chunks UNIQUE (document_id, chunk_index)
audit_logs (run_id, created_at)
```

### 12.4 Migration 流程

```text
修改 SQLAlchemy Model
↓
生成 Alembic Migration
↓
人工检查 upgrade 和 downgrade
↓
执行 upgrade
↓
执行 downgrade
↓
重新执行 upgrade
↓
运行自动化测试
↓
检查关键查询计划
```

禁止手动进入数据库绕过 Migration 修改结构。

---

## 13. API 统一规范

### 13.1 路径与版本

- API 使用资源导向的复数名词。
- 当前内部 API 保留 `/api/...`。
- 第一次对外发布稳定契约前确定 `/api/v1` 或 Header Versioning。
- 页面组件不得直接拼接请求 URL。

### 13.2 HTTP 语义

```text
GET     安全且幂等地读取
POST    创建资源或启动异步任务
PUT     完整替换
PATCH   部分更新
DELETE  幂等删除或标记删除
```

异步创建 Agent Run 返回：

```http
202 Accepted
Location: /api/agent/runs/{run_id}
```

### 13.3 成功和错误响应

成功响应直接返回资源或分页集合，不强制包裹统一 `{code, message, data}` 信封。

错误统一采用 RFC 7807 风格：

```json
{
  "type": "https://paris-agent.local/problems/resource-not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Agent run was not found.",
  "instance": "/api/agent/runs/...",
  "code": "AGENT_RUN_NOT_FOUND",
  "trace_id": "..."
}
```

至少稳定区分：

```text
VALIDATION_ERROR
UNAUTHORIZED
FORBIDDEN
RESOURCE_NOT_FOUND
CONFLICT
RATE_LIMITED
INTERNAL_ERROR
```

### 13.4 分页、过滤和幂等

- 列表默认使用游标分页。
- `limit` 必须有默认值和最大值。
- 排序字段使用白名单。
- 创建类接口在客户端可能重试时支持 `Idempotency-Key`。
- 重复幂等请求返回同一资源，不创建重复 Run 或任务。

### 13.5 认证和资源归属

- `user_id` 来自认证上下文，不信任客户端任意提交。
- Repository 查询必须带资源归属条件。
- 项目资源通过 `project_members` 授权。
- 接入真实多用户后评估 PostgreSQL Row-Level Security，但不能用 RLS 替代应用授权。

### 13.6 领域 API

```http
# Agent
POST /api/agent/runs
GET  /api/agent/runs/{run_id}
GET  /api/agent/runs/{run_id}/events
GET  /api/agent/runs/{run_id}/trace
POST /api/agent/runs/{run_id}/cancel
POST /api/agent/runs/{run_id}/resume

# Skills
GET  /api/skills
GET  /api/skills/{skill_id}
POST /api/skills/{skill_id}/runs

# Memory
GET    /api/memories
POST   /api/memories
PATCH  /api/memories/{memory_id}
DELETE /api/memories/{memory_id}

# Knowledge
POST   /api/knowledge/documents
GET    /api/knowledge/documents
GET    /api/knowledge/documents/{document_id}
DELETE /api/knowledge/documents/{document_id}
GET    /api/knowledge/chunks
POST   /api/knowledge/search

# Tools
GET  /api/tools
GET  /api/tool-calls
POST /api/tool-calls/{tool_call_id}/approval

# Evaluation
POST /api/eval/rag/runs
GET  /api/eval/rag/runs
GET  /api/eval/rag/runs/{eval_id}
```

这些路径属于目标设计。进入阶段前必须补充请求、响应、错误、权限和幂等契约。

---

## 14. Agent Run 与 SSE 契约

### 14.1 Run 状态

统一状态：

```text
queued
running
waiting_approval
succeeded
failed
cancelled
```

禁止在 Agent Run 中混用 `success` 和 `succeeded`。

合法迁移：

```text
queued -> running
queued -> cancelled
running -> waiting_approval
running -> succeeded
running -> failed
running -> cancelled
waiting_approval -> running
waiting_approval -> cancelled
```

终态不可恢复为运行态。需要重试整个 Run 时创建新 Run，并记录来源 Run。

### 14.2 稳定事件信封目标

```json
{
  "event_id": "UUID",
  "event_type": "node.completed",
  "run_id": "UUID",
  "sequence": 4,
  "timestamp": "2026-06-14T00:00:00Z",
  "status": "running",
  "payload": {
    "node_id": "n2",
    "node_name": "hybrid_search",
    "output": {}
  }
}
```

P2 已实现的扁平事件字段继续兼容到 P4 专项迁移完成。

### 14.3 事件类型

```text
run.started
run.waiting_approval
run.resumed
run.completed
run.failed
run.cancelled
skill.matched
skill.started
skill.completed
node.started
node.completed
node.failed
message.delta
message.completed
tool.started
tool.approval_required
tool.completed
tool.failed
checkpoint.created
safety.blocked
```

### 14.4 SSE 可靠性

- 同一 Run 的 `sequence` 从 1 单调递增。
- 数据库约束 `UNIQUE (run_id, sequence)`。
- SSE `id` 对应可恢复事件标识。
- 客户端发送 `Last-Event-ID`，服务端回放缺失事件。
- 服务端定期发送 SSE 注释心跳。
- 客户端按 `event_id` 或 `(run_id, sequence)` 去重。
- 终止事件发送后关闭该 Run 的流。
- 事件先持久化，再广播；RabbitMQ 不是事件事实存储。

---

## 15. 前端架构

### 15.1 页面路由

```text
/dashboard
/chat
/knowledge/documents
/knowledge/chunks
/memory
/skills
/skills/:skillId
/tools
/tools/audit
/runs
/runs/:runId
/eval
/eval/:evalId
/sandbox
/monitoring
/settings
```

登录页在引入真实认证时实现，不能用前端伪登录代替后端认证。

### 15.2 ChatPage 布局

```text
左侧：Paris Agent、导航、会话/项目/Skill 占位
中间：聊天消息和输入框
右侧：Agent Runtime 面板
```

P3 只显示：

```text
run_id
status
current_node
events
mock assistant response
```

Skill、DAG、Tool、Memory、Source、Checkpoint、Trace 和 Safety 面板在对应阶段逐步启用。

### 15.3 状态职责

```text
Axios Client
  REST 基础 URL、超时、请求和错误转换

TanStack Query
  服务端查询缓存、失效、分页和查询重试

Pinia
  当前会话、活跃 Run、SSE 增量、用户选择和页面交互状态

EventSource Wrapper
  SSE URL、事件解析、去重、重连和关闭
```

不得同时用 Pinia 和 TanStack Query 保存同一份服务端列表缓存。

### 15.4 开发代理

P3-P4 开发环境使用 Vite 同源代理将 `/api` 转发到后端，避免 REST 和 SSE 的浏览器
CORS 问题。生产环境由反向代理统一域名；若未来需要跨域部署，再增加显式 CORS 白名单。

---

## 16. 可观测性与成本

### 16.1 Trace 层级

```text
Run Span
├── Guardrail Span
├── Skill Router Span
├── Memory Retrieval Span
├── RAG Retrieval Span
│   ├── Milvus Span
│   ├── Elasticsearch Span
│   └── Neo4j Span
├── Planner Span
├── DAG Node Spans
├── Tool Call Spans
├── Verifier Span
└── Memory Writer Span
```

### 16.2 核心指标

```text
Run 成功率、失败率和取消率
平均与 P95/P99 延迟
首 token 延迟
平均节点数和工具调用数
模型输入/输出 token
模型和 Skill 成本
队列长度、等待时间和重试次数
工具成功率和安全拦截次数
RAG 检索耗时和命中质量
SSE 活跃连接和重连次数
```

成本明细不能只保存在 `agent_runs.total_cost`。后续需要不可变 usage event，记录模型、
供应商、输入/输出 token、单价、币种和关联节点。

---

## 17. 测试、迁移与发布门槛

### 17.1 后端测试层级

```text
Unit
  状态迁移、DAG 校验、评分、路由和策略

Repository
  PostgreSQL 约束、事务和查询

API Contract
  请求、响应、错误、认证和幂等

Integration
  PostgreSQL、Redis、RabbitMQ 和外部适配器

End-to-End
  创建 Run、SSE、工具审批、RAG 和 Sandbox 关键流程
```

### 17.2 前端验证

- TypeScript 构建通过。
- 页面在 1280px 和常见笔记本尺寸可用。
- REST 成功、失败和超时状态可见。
- SSE 增量、终止、断线和重复事件行为可验证。
- 输入按钮防重复提交。
- Run 切换或页面卸载时关闭旧 EventSource。

### 17.3 每阶段完成门槛

```text
专项契约已确认
Model 和 Migration 一致
API/OpenAPI 与前端类型一致
自动测试通过
手动闭环验证通过
.env.example 已同步
运行命令可复现
已知限制已记录
没有越级实现后续大型子系统
```

---

## 18. P0-P16 分步骤需求实现菜单

以下编号严格对齐 `AGENTS.md`。

### P0：项目骨架

**状态：** `[已实现]`

**目标：** 建立可启动的 backend、frontend、docker、docs 和 scripts。

**需求：**

- FastAPI、uv、pyproject.toml 和 uv.lock。
- Vue 3、TypeScript、Vite、pnpm 和基础路由。
- Docker Compose 启动 PostgreSQL、Redis、RabbitMQ。
- `.env.example`、`.gitignore` 和 README。

**验证：**

```powershell
Set-Location backend
uv sync
uv run uvicorn app.main:app --reload

Set-Location ..\frontend
pnpm install
pnpm dev

Set-Location ..\docker
docker compose up -d
docker compose ps
```

**完成标准：** 三端可启动，秘密不进入 Git。

**本阶段不做：** Agent Runtime、RAG、Skill 和 Sandbox。

### P1：后端 health check + 前端基础布局

**状态：** `[已实现]`

**前置依赖：** P0。

**后端：** `/health` 返回服务和环境状态。

**前端：** WorkbenchLayout、DashboardPage、Paris Agent 品牌和基础导航。

**测试：** 后端 health API 测试、前端 `pnpm build`。

**完成标准：** 浏览器可查看基础页面，health 返回 200。

**本阶段不做：** ChatPage 和 Agent Run。

### P2：Agent Run mock

**状态：** `[已实现]`

**前置依赖：** P1、PostgreSQL 和 Alembic。

**后端：**

- `agent_runs` Model、Repository 和 Migration。
- `POST /api/agent/runs`。
- `GET /api/agent/runs/{run_id}`。
- 进程内 Mock Runner。

**数据库：** UUID 业务 ID、状态 CHECK、TIMESTAMPTZ、成本和查询索引。

**测试：** 创建、查询、成功、失败、404 和数据库约束。

**完成标准：** Run 从 `queued` 进入 `running`，最终进入终态并持久化。

**本阶段不做：** LangGraph、Skill、RAG、工具、队列和 Sandbox。

### P3：ChatPage mock

**状态：** `[已实现]`

**前置依赖：** P2。

**前端：**

- 新增 `/chat`。
- 创建 ChatPage、AgentChat、ChatMessage、MessageInput、AgentRunPanel。
- 创建 `src/api/agent.ts` 和 Agent Run Pinia Store。
- 通过 Vite `/api` 代理调用 POST 和 GET。
- 展示 run_id、status、current_node 和模拟回复。

**接口：** 复用 P2 REST 契约。

**验证：** `pnpm build`；手动创建 Run 并查看最终状态。

**完成标准：** 用户输入一句话后能够看到持久化 Run 和模拟回复。

**本阶段不做：** 完整 Runtime 面板和持久 SSE 恢复。

### P4：SSE 事件流

**状态：** `[部分实现]`

**前置依赖：** P2、P3。

**后端：**

- 保留当前 mock SSE。
- 新增 `runtime_events` Model 和 Migration。
- 事件先持久化再广播。
- 支持 sequence、心跳、`Last-Event-ID` 和终止事件。

**前端：**

- EventSource 封装。
- `message.delta` 增量显示。
- 节点和 Run 事件更新右侧面板。
- 断线重连、去重和卸载清理。

**测试：** 事件顺序、回放、重连、重复事件、未知 Run 和终止关闭。

**完成标准：** 服务短暂断连后不会丢失或重复展示已持久化事件。

**本阶段不做：** RabbitMQ 多实例广播，可先采用 PostgreSQL 回放和单实例通知。

### P5：Skill Registry

**状态：** `[未开始]`

**前置依赖：** P4。

**后端：**

- Skill YAML Schema、Loader、Validator 和 Registry。
- `agent_skills`、`agent_skill_versions`。
- `GET /api/skills`、`GET /api/skills/{skill_id}`。
- 显式 Skill 选择和默认路由占位。

**前端：** SkillSelector、SlashCommandMenu 初版。

**测试：** 合法/非法 YAML、重复版本、禁用 Skill 和未知 Skill。

**完成标准：** 能列出版本化 Skill，并让 Run 记录 Skill 版本。

**本阶段不做：** 复杂 LLM 自动路由和完整 DAG 执行。

### P6：长期记忆 V1

**状态：** `[未开始]`

**前置依赖：** P5、用户归属契约。

**后端：**

- `agent_memories` Model 和 Migration。
- Memory Repository、Manager、Extractor Mock 和 Retriever。
- 创建、查询、更新和删除 API。
- 权限、来源、importance、confidence、版本和过期规则。

**前端：** MemoryPage、MemoryList、MemoryEditor。

**测试：** 用户隔离、范围约束、去重、过期和删除。

**完成标准：** 可管理结构化记忆并在 mock Run 中检索。

**本阶段不做：** Milvus 记忆向量和复杂自动合并。

### P7：文档上传 + 基础 RAG

**状态：** `[未开始]`

**前置依赖：** P6、Milvus。

**后端：**

- documents、document_chunks 和 Migration。
- 上传、文件校验、解析、Chunk 和 Embedding。
- Milvus Dense Retrieval。
- 返回答案引用的 Chunk 来源。

**前端：** DocumentUploader、DocumentTable、KnowledgeSourceList。

**测试：** 文件类型/大小、解析失败、Chunk 唯一性、检索和引用。

**完成标准：** 上传文档后可通过 Dense Retrieval 返回可追溯来源。

**本阶段不做：** BM25、GraphRAG 和异步队列。

### P8：RabbitMQ + Celery

**状态：** `[未开始]`

**前置依赖：** P7。

**后端：**

- 消息信封和 Schema Version。
- Transactional Outbox。
- 文档解析和 Embedding Celery Task。
- Retry、DLQ、幂等消费和任务状态。

**前端：** 展示异步文档处理状态。

**测试：** 重复投递、Worker 重启、重试上限、DLQ 和状态一致性。

**完成标准：** 文档任务异步执行且重复消息不产生重复 Chunk。

**本阶段不做：** Sandbox 和复杂 Agent Runtime。

### P9：Tool Registry

**状态：** `[未开始]`

**前置依赖：** P8。

**后端：**

- Tool Schema、Registry、Manager 和 Guardrail。
- safe/low/medium/high/block 风险规则。
- agent_tool_calls 和 audit_logs。
- 审批 API 和 Mock Tool。

**前端：** ToolCallTimeline、ToolApprovalDialog。

**测试：** Schema、权限、风险、审批、拒绝、超时和审计。

**完成标准：** 所有工具只能经 Tool Manager 执行并产生审计记录。

**本阶段不做：** 真正宿主机 Shell 和生产 Sandbox。

### P10：DAG ReAct Runtime

**状态：** `[未开始]`

**前置依赖：** P9。

**后端：**

- DAGPlan、DAGValidator、DependencyResolver。
- TopologicalScheduler 和 ParallelNodeExecutor。
- agent_node_states。
- 节点事件和状态持久化。

**前端：** DAGRuntimeViewer。

**测试：** 环检测、缺失依赖、并行组、失败传播和取消。

**完成标准：** 一个多节点 Mock DAG 可按依赖并行执行并完整展示。

**本阶段不做：** Checkpoint、Retry、Fallback 和 Sandbox。

### P11：Harness Checkpoint / Retry / Fallback

**状态：** `[未开始]`

**前置依赖：** P10。

**后端：**

- RunManager、StateManager、CheckpointManager。
- Retry、Fallback 和 Timeout Policy。
- agent_checkpoints。
- LangGraph Checkpointer 适配和恢复入口。

**前端：** RunDetailPage、CheckpointList、TraceTimeline。

**测试：** 节点重试、超时、Fallback、进程重启恢复和幂等恢复。

**完成标准：** 故障 Run 能从合法 Checkpoint 恢复且不重复副作用。

**本阶段不做：** 真实代码执行。

### P12：Docker Sandbox

**状态：** `[未开始]`

**前置依赖：** P9、P11。

**后端：**

- Sandbox Tool Adapter。
- 镜像白名单、非 root、网络和资源隔离。
- 超时、输出限制、临时文件清理。
- 高风险审批和完整审计。

**前端：** SandboxConsole。

**测试：** 网络阻断、资源限制、超时、危险命令、并发和清理。

**完成标准：** 代码只能在受限容器中执行，宿主机不暴露。

**本阶段不做：** 任意镜像和宿主机 Shell。

### P13：Hybrid RAG

**状态：** `[未开始]`

**前置依赖：** P7、P8、Elasticsearch。

**后端：**

- BM25 索引和检索。
- Dense 与 BM25 双路召回。
- RRF 融合和可配置参数。
- 外部索引同步状态与重建任务。

**前端：** 展示来源类型、分数和融合排名。

**测试：** 索引一致性、召回、融合、降级和重建。

**完成标准：** Hybrid 检索可与 Dense Only 进行可重复对比。

**本阶段不做：** Neo4j 图检索。

### P14：GraphRAG

**状态：** `[未开始]`

**前置依赖：** P13、Neo4j。

**后端：**

- Entity/Relation Schema。
- 实体抽取、消歧、关系写入和同步状态。
- Graph Retrieval 与 Hybrid 结果融合。
- Memory Graph 边界设计。

**前端：** 知识实体关系和图来源查看。

**测试：** 重复实体、关系版本、同步失败、图召回和来源追溯。

**完成标准：** 图上下文能提升指定 Golden Query，并可追溯原文。

**本阶段不做：** 无来源的自动事实写入。

### P15：RAG 评测

**状态：** `[未开始]`

**前置依赖：** P13，可选 P14。

**后端：**

- Golden Query 数据集和版本。
- rag_eval_tasks、rag_eval_results。
- Recall@K、MRR、NDCG、HitRate。
- Faithfulness、Answer Relevancy、Context Precision/Recall。
- Dense、Hybrid、Graph 和 Rerank 对比。

**前端：** EvalPage、EvalMetricChart。

**测试：** 指标公式、数据集版本、任务重试和报告复现。

**完成标准：** 同一版本数据集可重复生成策略对比报告。

**本阶段不做：** 用单一 LLM Judge 分数代替全部质量判断。

### P16：监控与可观测性

**状态：** `[未开始]`

**前置依赖：** P11-P15 的核心事件和 Trace。

**后端与基础设施：**

- OpenTelemetry Trace、Metric 和 Log Correlation。
- Prometheus 指标。
- Grafana Dashboard 和告警。
- 模型 usage event 和成本聚合。

**前端：** MonitoringPage、MetricCard 和关键 Trace 跳转。

**测试：** Trace 贯通、指标标签基数、告警规则和敏感信息脱敏。

**完成标准：** Run、节点、工具、队列、RAG 和成本可统一定位。

**本阶段不做：** 记录 Prompt、密钥或用户敏感数据到不受控日志。

---

## 19. Codex 单步任务模板

```text
请根据 AGENTS.md、docs/FULLSTACK_TECH_DESIGN.md 和本阶段专项契约，
只实现【阶段编号 / 小步名称】。

任务目标：
前置依赖：
本次范围：
明确不做：
需要修改的文件：
数据结构：
API / SSE / 消息契约：
数据库与 Alembic：
自动测试：
手动验证：
完成标准：

要求：
1. 先阅读文档和相关源码。
2. 先输出计划和修改文件。
3. 先定义类型和接口，再写实现。
4. 不新增无关依赖。
5. 后端使用 uv，前端使用 pnpm。
6. 数据库结构只通过 Alembic 修改。
7. 配置通过 .env 和 .env.example 管理。
8. 完成后输出修改文件、命令、验证结果和已知限制。
```

---

## 20. 设计变更规则

- 跨模块契约变化先更新主设计或专项契约，再修改实现。
- 破坏性 API、SSE 或消息变化必须提供版本或兼容迁移。
- 阶段编号只允许在 `AGENTS.md` 中定义。
- 每次只实现一个可验证的小闭环。
- 设计文档不能替代测试，测试也不能替代明确契约。
