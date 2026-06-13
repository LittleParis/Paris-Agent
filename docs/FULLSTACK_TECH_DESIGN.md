# FULLSTACK_TECH_DESIGN.md

# Paris Agent 前后端一体化技术设计文档

## 1. 项目概述

### 1.1 项目名称

Paris Agent：面向程序员技术学习场景的 Skill-based Agent Workbench

### 1.2 项目定位

本项目面向程序员技术学习、知识检索、代码理解、学习路线规划、项目知识沉淀和 Agent 工程实践，构建一个具备 Skill-based Agent Workflow、自研长期记忆系统、Hybrid GraphRAG、动态图 ReAct Runtime、Agent Harness 容错执行引擎、多层安全校验、Docker Sandbox、RabbitMQ 异步任务、RAG 评测和可观测性追踪的全栈 AI Agent 系统。

项目不是普通 ChatBot，而是一个可视化 Agent Workbench。用户可以在前端完成：

```text
技术问答
学习路线生成
文档上传与知识库构建
长期记忆管理
Skill 调用
工具调用审批
代码沙箱执行
Agent Run Trace 查看
RAG 评测
系统监控
```

---

## 2. 技术选型

### 2.1 后端技术栈

```text
Python 3.11+
FastAPI
LangGraph
PostgreSQL
SQLAlchemy
Alembic
Redis
RabbitMQ
Celery
Milvus
Elasticsearch
Neo4j
Docker Sandbox
OpenTelemetry
Prometheus
Grafana
RAGAS
LiteLLM，可选
```

### 2.2 前端技术栈

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
Markdown Renderer
```

### 2.3 依赖管理

后端：

```text
uv + pyproject.toml + uv.lock
```

前端：

```text
pnpm + package.json + pnpm-lock.yaml
```

中间件：

```text
Docker Compose
```

配置：

```text
.env.example + .env
```

数据库迁移：

```text
Alembic
```

---

## 3. 总体架构

```text
Vue 3 Frontend
├── ChatPage
├── SkillSelector
├── DAGRuntimeViewer
├── ToolCallTimeline
├── MemoryPage
├── KnowledgePage
├── SandboxPage
├── EvalPage
└── MonitoringPage
        ↓
FastAPI Gateway
        ↓
Skill Router
        ↓
Skill Registry
        ↓
Skill Executor
        ↓
Agent Harness
├── Input Guardrail
├── Intent Classifier
├── Memory Retriever
├── Hybrid Retriever
├── Planner
├── DAG ReAct Runtime
├── Tool Manager
├── Verifier
├── Output Guardrail
└── Memory Writer
        ↓
Infrastructure
├── PostgreSQL
├── Redis
├── RabbitMQ
├── Milvus
├── Elasticsearch
├── Neo4j
├── Docker Sandbox
├── OpenTelemetry
├── Prometheus
└── Grafana
```

---

## 4. 项目目录结构

### 4.1 根目录

```text
paris-agent/
├── backend/
├── frontend/
├── docker/
├── docs/
├── scripts/
├── AGENTS.md
├── .gitignore
└── README.md
```

### 4.2 后端目录

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── routes_agent.py
│   │   ├── routes_skills.py
│   │   ├── routes_memory.py
│   │   ├── routes_knowledge.py
│   │   ├── routes_tools.py
│   │   ├── routes_eval.py
│   │   └── routes_monitoring.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── security.py
│   ├── db/
│   │   ├── session.py
│   │   ├── models.py
│   │   └── repositories/
│   ├── schemas/
│   │   ├── agent.py
│   │   ├── skill.py
│   │   ├── memory.py
│   │   ├── knowledge.py
│   │   ├── tool.py
│   │   └── eval.py
│   ├── agent/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── runtime/
│   │   └── nodes/
│   ├── skills/
│   │   ├── registry.py
│   │   ├── router.py
│   │   ├── executor.py
│   │   ├── loader.py
│   │   ├── schemas.py
│   │   └── definitions/
│   ├── memory/
│   ├── rag/
│   ├── tools/
│   ├── security/
│   ├── queue/
│   ├── eval/
│   └── observability/
├── alembic/
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── .env.example
└── README.md
```

### 4.3 前端目录

```text
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/
│   ├── api/
│   ├── stores/
│   ├── layouts/
│   ├── pages/
│   ├── components/
│   ├── composables/
│   ├── utils/
│   └── styles/
├── package.json
├── pnpm-lock.yaml
├── vite.config.ts
└── README.md
```

---

## 5. 核心业务场景

### 5.1 技术问答

用户输入：

```text
Kafka 为什么能够保证高吞吐？
```

执行流程：

```text
Skill Router 匹配 tech_qa
↓
检索长期学习记忆
↓
Hybrid RAG 检索技术资料
↓
GraphRAG 查询知识点关系
↓
LLM 基于上下文生成答案
↓
Verifier 检查回答是否忠实于资料
↓
返回答案、来源和相关知识点
```

---

### 5.2 学习路线生成

用户输入：

```text
我已经学过 Java、Spring Boot 和 MySQL，现在想学习 Kafka 和 Redis。
```

执行流程：

```text
Skill Router 匹配 learning_path
↓
读取用户学习画像
↓
查询技术知识图谱
↓
检索相关资料
↓
Planner 生成学习阶段
↓
task_create 创建学习任务
↓
memory_write 更新学习画像
```

---

### 5.3 文档入库

用户上传：

```text
Kafka PDF
Spring Boot Markdown
Redis 面试题 Word
项目 README
```

执行流程：

```text
上传文档
↓
保存文档元数据
↓
发送 RabbitMQ document.ingest 消息
↓
Worker 解析文档
↓
Chunk 切分
↓
发送 document.embedding 消息
↓
写入 Milvus
↓
写入 Elasticsearch
↓
抽取实体关系写入 Neo4j
```

---

### 5.4 代码沙箱执行

用户输入：

```text
运行这段 Python 代码，看看输出结果。
```

执行流程：

```text
Skill Router 匹配 code_sandbox
↓
Tool Risk Classifier 判断风险
↓
Permission Checker 检查权限
↓
必要时前端弹出审批
↓
Docker Sandbox 执行代码
↓
返回 stdout / stderr / exit_code
↓
RabbitMQ Audit Event
↓
Audit Worker 落库
```

---

### 5.5 RAG 评测

用户输入：

```text
评测当前知识库的检索效果。
```

执行流程：

```text
Skill Router 匹配 rag_eval
↓
加载 Golden Queries
↓
执行 Dense / BM25 / Graph / Hybrid 检索
↓
计算 Recall@K、MRR、NDCG、HitRate
↓
执行生成质量评测
↓
生成评测报告
```

---

## 6. Skill-based Agent Workflow 设计

### 6.1 Skill 定义

Skill 是一个能力包，用于封装某类任务的专用 Prompt、输入输出 Schema、工具集、执行流程、记忆策略和安全策略。

Skill 包含：

```text
id
name
description
version
enabled
input_schema
output_schema
prompt
tools
workflow
memory_policy
safety
runtime
```

---

### 6.2 Skill 调用方式

显式调用：

```text
/skill tech_qa Kafka 为什么能保证高吞吐？
```

隐式调用：

```text
帮我评测当前知识库效果
```

系统自动路由到：

```text
rag_eval
```

---

### 6.3 Skill 系统模块

```text
backend/app/skills/
├── registry.py
├── router.py
├── executor.py
├── loader.py
├── schemas.py
├── version_manager.py
├── run_logger.py
└── definitions/
    ├── tech_qa.yaml
    ├── learning_path.yaml
    ├── document_ingest.yaml
    ├── rag_eval.yaml
    ├── memory_consolidation.yaml
    ├── code_sandbox.yaml
    ├── project_summary.yaml
    └── codex_task.yaml
```

---

### 6.4 第一版核心 Skills

| Skill ID             | 名称         | 作用                |
| -------------------- | ---------- | ----------------- |
| tech_qa              | 技术问答       | 回答技术问题            |
| learning_path        | 学习路线       | 生成个性化学习路线         |
| document_ingest      | 文档入库       | 解析、切分、向量化文档       |
| rag_eval             | RAG 评测     | 评测检索和生成质量         |
| memory_consolidation | 记忆整理       | 去重、合并、更新记忆        |
| code_sandbox         | 代码沙箱       | 安全执行代码            |
| project_summary      | 项目总结       | 总结项目进度            |
| codex_task           | Codex 任务拆分 | 将需求拆成 Codex 可执行任务 |

---

### 6.5 Skill 配置示例

```yaml
id: tech_qa
name: 技术问答 Skill
description: 基于长期记忆、Hybrid RAG 和技术知识图谱回答程序员技术问题
version: 1.0.0
enabled: true

input_schema:
  question:
    type: string
    required: true
  project_id:
    type: string
    required: false

output_schema:
  answer:
    type: string
  sources:
    type: list
  related_concepts:
    type: list

tools:
  - memory_search
  - hybrid_search
  - graph_query

workflow:
  - node: memory_retriever
    type: memory
    tool: memory_search
  - node: hybrid_retriever
    type: rag
    tool: hybrid_search
  - node: graph_retriever
    type: graph
    tool: graph_query
  - node: answer_generator
    type: llm
  - node: verifier
    type: verifier

memory_policy:
  read: true
  write: true
  write_types:
    - episodic
    - learning_profile

safety:
  risk_level: low
  requires_approval: false

runtime:
  max_steps: 8
  max_tool_calls: 10
  max_runtime_seconds: 120
  checkpoint: true
```

---

## 7. Agent Harness 设计

### 7.1 Harness 定位

Agent Harness 是 Agent 的运行时外壳，负责状态、工具、安全、容错、追踪和恢复。

核心组件：

```text
RunManager
StateManager
CheckpointManager
RetryManager
FallbackManager
TimeoutManager
ToolIsolationManager
SchemaValidator
EventPublisher
TraceRecorder
CostManager
```

---

### 7.2 Agent 执行链路

```text
用户输入
↓
Input Guardrail
↓
Skill Router
↓
Skill Executor
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
Final Response
```

---

### 7.3 AgentState

```python
from typing import TypedDict, Any

class AgentState(TypedDict):
    run_id: str
    thread_id: str
    user_id: str
    project_id: str | None
    skill_id: str | None
    user_input: str
    intent: str | None
    messages: list[dict[str, Any]]
    memories: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    graph_context: list[dict[str, Any]]
    dag_plan: dict[str, Any] | None
    current_node: str | None
    node_states: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    final_answer: str | None
    error: str | None
    cost: dict[str, Any]
    metadata: dict[str, Any]
```

---

## 8. 动态图 ReAct Runtime 设计

### 8.1 设计目标

传统 ReAct 是串行模式：

```text
Thought → Action → Observation → Thought → Action → Observation
```

本项目升级为 DAG ReAct Runtime：

```text
Planner
↓
DAG Plan
├── memory_search
├── hybrid_search
├── graph_query
└── answer_generator
↓
Verifier
```

优势：

```text
可并行
可重试
可 fallback
可 checkpoint
可观测
可恢复
```

---

### 8.2 DAG Plan

```json
{
  "goal": "生成 Kafka 学习路线",
  "nodes": [
    {
      "node_id": "n1",
      "name": "检索用户学习记忆",
      "type": "tool",
      "tool": "memory_search",
      "depends_on": [],
      "parallel_group": "retrieval"
    },
    {
      "node_id": "n2",
      "name": "检索 Kafka 技术资料",
      "type": "tool",
      "tool": "hybrid_search",
      "depends_on": [],
      "parallel_group": "retrieval"
    },
    {
      "node_id": "n3",
      "name": "生成学习路线",
      "type": "llm",
      "depends_on": ["n1", "n2"]
    }
  ]
}
```

---

### 8.3 Runtime 组件

```text
DAGValidator
DependencyResolver
TopologicalScheduler
ParallelNodeExecutor
ReActNodeExecutor
NodeStateStore
RetryManager
FallbackManager
CheckpointManager
```

---

## 9. 自研长期记忆系统设计

### 9.1 记忆类型

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

### 9.2 记忆写入流程

```text
用户输入 / Agent 输出 / 工具结果
↓
Memory Extractor
↓
Memory Classifier
↓
Importance Scorer
↓
Confidence Scorer
↓
Embedding
↓
Similarity Search
↓
Deduplication
↓
Merge / Update
↓
PostgreSQL + Milvus
```

### 9.3 记忆检索评分

```text
final_score =
similarity * 0.45
+ importance * 0.25
+ recency * 0.15
+ access_weight * 0.10
+ project_relevance * 0.05
```

---

## 10. Hybrid GraphRAG 设计

### 10.1 检索组成

```text
Milvus Dense Retrieval
+
Elasticsearch BM25 Retrieval
+
Neo4j Graph Retrieval
```

### 10.2 检索流程

```text
用户问题
↓
Query Rewrite
↓
Milvus 向量召回
↓
Elasticsearch BM25 召回
↓
Neo4j 图谱召回
↓
RRF 融合排序
↓
Context Builder
↓
LLM Answer
↓
Verifier
```

### 10.3 RRF 融合

```text
score(d) = Σ 1 / (k + rank_i(d))
```

默认参数：

```text
k = 60
top_k_dense = 10
top_k_sparse = 10
top_k_graph = 10
final_top_k = 8
```

---

## 11. Tool Registry 设计

### 11.1 工具元数据

```json
{
  "name": "code_execute",
  "description": "在 Docker Sandbox 中执行代码",
  "input_schema": {
    "language": "string",
    "code": "string",
    "timeout": "integer"
  },
  "risk_level": "high",
  "requires_approval": true,
  "enabled": true
}
```

### 11.2 核心工具

| 工具            | 作用            | 风险     |
| ------------- | ------------- | ------ |
| memory_search | 查询长期记忆        | safe   |
| memory_write  | 写入长期记忆        | low    |
| hybrid_search | Hybrid RAG 检索 | safe   |
| graph_query   | 查询 Neo4j 图谱   | safe   |
| task_create   | 创建学习任务        | medium |
| doc_generate  | 生成文档          | medium |
| code_execute  | 执行代码          | high   |
| shell_execute | 执行 Shell      | high   |

工具调用必须经过：

```text
Tool Manager
↓
Tool Guardrail
↓
Permission Checker
↓
Tool Executor
↓
Audit Logger
```

---

## 12. 多层安全与 Docker Sandbox

### 12.1 安全链路

```text
Input Guardrail
↓
Intent Risk Classifier
↓
Tool Risk Classifier
↓
Permission Checker
↓
Docker Sandbox
↓
Output Guardrail
↓
Audit Logger
```

### 12.2 Docker Sandbox 参数

```text
--network none
--read-only
--cap-drop ALL
--security-opt no-new-privileges
--memory 256m
--cpus 0.5
--pids-limit 64
```

### 12.3 危险命令拦截

```text
rm -rf /
mkfs
dd
shutdown
reboot
curl
wget
nc
ssh
scp
chmod 777 /
sudo
su
mount
umount
iptables
```

---

## 13. RabbitMQ / Celery 设计

### 13.1 Exchange

```text
Exchange: paris.agent.events
Type: topic
```

### 13.2 Queue

| Queue                    | Routing Key        | 说明       |
| ------------------------ | ------------------ | -------- |
| document.ingest.queue    | document.ingest    | 文档解析     |
| document.embedding.queue | document.embedding | 向量化      |
| agent.run.events.queue   | agent.run.*        | Agent 事件 |
| tool.audit.logs.queue    | tool.audit.*       | 工具审计     |
| rag.eval.tasks.queue     | rag.eval.*         | RAG 评测   |
| cost.usage.events.queue  | cost.usage.*       | 成本统计     |
| sandbox.exec.queue       | sandbox.exec.*     | 沙箱执行     |

---

## 14. 数据库设计

### 14.1 agent_runs

```sql
CREATE TABLE agent_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) UNIQUE NOT NULL,
    thread_id VARCHAR(64),
    user_id VARCHAR(64),
    project_id VARCHAR(64),
    skill_id VARCHAR(64),
    task_type VARCHAR(64),
    status VARCHAR(32),
    current_node VARCHAR(64),
    input TEXT,
    final_output TEXT,
    error_message TEXT,
    total_tokens INT DEFAULT 0,
    total_cost NUMERIC(10, 6) DEFAULT 0,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 14.2 agent_steps

```sql
CREATE TABLE agent_steps (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64),
    step_index INT,
    step_name VARCHAR(128),
    node_name VARCHAR(128),
    status VARCHAR(32),
    input JSONB,
    output JSONB,
    error_message TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP
);
```

### 14.3 agent_node_states

```sql
CREATE TABLE agent_node_states (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64),
    node_id VARCHAR(64),
    node_name VARCHAR(128),
    node_type VARCHAR(64),
    status VARCHAR(32),
    depends_on JSONB,
    input JSONB,
    output JSONB,
    retry_count INT DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP
);
```

### 14.4 agent_tool_calls

```sql
CREATE TABLE agent_tool_calls (
    id BIGSERIAL PRIMARY KEY,
    tool_call_id VARCHAR(128) UNIQUE NOT NULL,
    run_id VARCHAR(64),
    node_id VARCHAR(64),
    tool_name VARCHAR(128),
    input JSONB,
    output JSONB,
    status VARCHAR(32),
    risk_level VARCHAR(32),
    requires_approval BOOLEAN DEFAULT FALSE,
    approved_by VARCHAR(64),
    latency_ms INT,
    created_at TIMESTAMP
);
```

### 14.5 agent_checkpoints

```sql
CREATE TABLE agent_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    checkpoint_id VARCHAR(64) UNIQUE NOT NULL,
    run_id VARCHAR(64),
    thread_id VARCHAR(64),
    node_name VARCHAR(128),
    node_id VARCHAR(64),
    state_snapshot JSONB,
    next_nodes JSONB,
    created_at TIMESTAMP
);
```

### 14.6 agent_memories

```sql
CREATE TABLE agent_memories (
    id BIGSERIAL PRIMARY KEY,
    memory_id VARCHAR(64) UNIQUE NOT NULL,
    user_id VARCHAR(64),
    project_id VARCHAR(64),
    memory_type VARCHAR(32),
    content TEXT,
    summary TEXT,
    importance FLOAT,
    confidence FLOAT,
    source VARCHAR(64),
    tags TEXT[],
    milvus_id VARCHAR(128),
    version INT DEFAULT 1,
    access_count INT DEFAULT 0,
    last_accessed_at TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    expires_at TIMESTAMP
);
```

### 14.7 agent_skills

```sql
CREATE TABLE agent_skills (
    id BIGSERIAL PRIMARY KEY,
    skill_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128),
    description TEXT,
    version VARCHAR(32),
    config JSONB,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 14.8 agent_skill_runs

```sql
CREATE TABLE agent_skill_runs (
    id BIGSERIAL PRIMARY KEY,
    skill_run_id VARCHAR(64) UNIQUE NOT NULL,
    skill_id VARCHAR(64),
    skill_version VARCHAR(32),
    run_id VARCHAR(64),
    user_id VARCHAR(64),
    project_id VARCHAR(64),
    input JSONB,
    output JSONB,
    status VARCHAR(32),
    error_message TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 14.9 documents

```sql
CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    document_id VARCHAR(64) UNIQUE NOT NULL,
    user_id VARCHAR(64),
    title VARCHAR(255),
    file_type VARCHAR(32),
    file_path TEXT,
    status VARCHAR(32),
    chunk_count INT DEFAULT 0,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 14.10 document_chunks

```sql
CREATE TABLE document_chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id VARCHAR(64) UNIQUE NOT NULL,
    document_id VARCHAR(64),
    title VARCHAR(255),
    content TEXT,
    page_number INT,
    chunk_index INT,
    milvus_id VARCHAR(128),
    elastic_id VARCHAR(128),
    tags TEXT[],
    created_at TIMESTAMP
);
```

### 14.11 audit_logs

```sql
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    audit_id VARCHAR(64) UNIQUE NOT NULL,
    run_id VARCHAR(64),
    user_id VARCHAR(64),
    tool_call_id VARCHAR(128),
    event_type VARCHAR(64),
    risk_level VARCHAR(32),
    input_hash VARCHAR(128),
    status VARCHAR(32),
    sandbox_enabled BOOLEAN DEFAULT FALSE,
    detail JSONB,
    created_at TIMESTAMP
);
```

---

## 15. 后端 API 设计

### 15.1 Agent API

```http
POST /api/agent/runs
GET /api/agent/runs/{run_id}
GET /api/agent/runs/{run_id}/events
GET /api/agent/runs/{run_id}/trace
POST /api/agent/runs/{run_id}/stop
POST /api/agent/runs/{run_id}/resume
```

### 15.2 Skill API

```http
GET /api/skills
GET /api/skills/{skill_id}
POST /api/skills/{skill_id}/run
GET /api/skills/runs
GET /api/skills/runs/{skill_run_id}
```

### 15.3 Memory API

```http
GET /api/memories
POST /api/memories
PUT /api/memories/{memory_id}
DELETE /api/memories/{memory_id}
```

### 15.4 Knowledge API

```http
POST /api/knowledge/documents
GET /api/knowledge/documents
GET /api/knowledge/documents/{document_id}
DELETE /api/knowledge/documents/{document_id}
GET /api/knowledge/chunks
POST /api/knowledge/search
```

### 15.5 Tool API

```http
GET /api/tools
GET /api/tools/calls
POST /api/tools/{tool_name}/execute
POST /api/tools/calls/{tool_call_id}/approve
```

### 15.6 Eval API

```http
POST /api/eval/rag
GET /api/eval/tasks
GET /api/eval/tasks/{eval_id}
```

---

## 16. SSE 事件设计

Agent Run 通过 SSE 向前端推送事件。

接口：

```http
GET /api/agent/runs/{run_id}/events
```

事件类型：

```text
message.delta
message.completed
node.started
node.completed
node.failed
tool.started
tool.completed
tool.approval_required
checkpoint.created
skill.matched
skill.started
skill.completed
run.completed
run.failed
```

事件示例：

```json
{
  "event_type": "node.completed",
  "run_id": "run_001",
  "node_id": "n2",
  "node_name": "hybrid_search",
  "status": "success",
  "latency_ms": 850
}
```

---

## 17. 前端页面设计

### 17.1 页面路由

```text
/login
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

### 17.2 ChatPage 布局

```text
左侧：会话列表 / 项目列表 / Skill 快捷入口
中间：聊天消息区
右侧：Agent Runtime 面板
```

右侧面板包含：

```text
当前 Skill
DAG Runtime
Tool Calls
Memories
Retrieved Sources
Checkpoints
Trace
Safety Events
```

---

## 18. 前端核心组件

```text
AgentChat
ChatMessage
MessageInput
SkillSelector
SlashCommandMenu
SkillRunPanel
AgentRunPanel
DAGRuntimeViewer
ToolCallTimeline
ToolApprovalDialog
MemoryList
MemoryEditor
DocumentUploader
DocumentTable
KnowledgeSourceList
SandboxConsole
TraceTimeline
EvalMetricChart
MetricCard
```

---

## 19. 前端 Store 设计

```text
authStore
chatStore
runStore
skillStore
memoryStore
knowledgeStore
toolStore
evalStore
sandboxStore
monitoringStore
settingsStore
```

---

## 20. 前端 API Client

```text
frontend/src/api/
├── http.ts
├── agent.ts
├── skills.ts
├── memory.ts
├── knowledge.ts
├── tools.ts
├── eval.ts
├── sandbox.ts
├── monitoring.ts
└── types.ts
```

---

## 21. 前端核心类型

### 21.1 AgentRun

```typescript
export interface AgentRun {
  run_id: string
  thread_id: string
  user_id: string
  project_id?: string
  skill_id?: string
  task_type?: string
  status: 'queued' | 'running' | 'success' | 'failed' | 'cancelled' | 'waiting_approval'
  current_node?: string
  input: string
  final_output?: string
  error_message?: string
  total_tokens: number
  total_cost: number
  created_at: string
  updated_at: string
}
```

### 21.2 Skill

```typescript
export interface Skill {
  skill_id: string
  name: string
  description: string
  version: string
  enabled: boolean
  risk_level?: 'safe' | 'low' | 'medium' | 'high' | 'block'
  tools: string[]
}
```

### 21.3 DAGNode

```typescript
export interface DAGNode {
  node_id: string
  node_name: string
  node_type: 'llm' | 'tool' | 'rag' | 'memory' | 'verifier' | 'guardrail'
  status: 'pending' | 'running' | 'success' | 'failed' | 'retrying' | 'fallback' | 'skipped'
  depends_on: string[]
  input?: Record<string, any>
  output?: Record<string, any>
  retry_count: number
  latency_ms?: number
  error_message?: string
}
```

### 21.4 Memory

```typescript
export interface Memory {
  memory_id: string
  user_id: string
  project_id?: string
  memory_type: string
  content: string
  summary?: string
  importance: number
  confidence: number
  tags: string[]
  source: string
  access_count: number
  created_at: string
  updated_at: string
  expires_at?: string
}
```

### 21.5 ToolCall

```typescript
export interface ToolCall {
  tool_call_id: string
  run_id: string
  node_id?: string
  tool_name: string
  input: Record<string, any>
  output?: Record<string, any>
  status: 'pending' | 'running' | 'success' | 'failed' | 'blocked' | 'waiting_approval'
  risk_level: 'safe' | 'low' | 'medium' | 'high' | 'block'
  requires_approval: boolean
  latency_ms?: number
  created_at: string
}
```

---

## 22. RAG 评测设计

### 22.1 评测指标

```text
Recall@K
MRR
NDCG
HitRate
Faithfulness
Answer Relevancy
Context Precision
Context Recall
```

### 22.2 对比策略

```text
Dense Only
BM25 Only
Graph Only
Dense + BM25
Dense + BM25 + Graph
Hybrid + RRF
Hybrid + Rerank
```

---

## 23. 可观测性设计

### 23.1 Trace 结构

```text
Run
├── Skill Router
├── Input Guardrail
├── Memory Retrieval
├── Hybrid Retrieval
│   ├── Milvus Search
│   ├── Elasticsearch Search
│   └── Neo4j Query
├── Planner
├── DAG ReAct Nodes
├── Tool Calls
├── Verifier
├── Output Guardrail
└── Memory Writer
```

### 23.2 核心指标

```text
Run 成功率
Run 失败率
平均响应时间
P95 延迟
平均 step 数
平均 tool call 数
模型调用次数
输入 token
输出 token
总成本
RabbitMQ 队列长度
Worker 数量
工具成功率
安全拦截次数
RAG 检索耗时
```

---

## 24. MVP 实现规划

### P0：项目骨架

目标：

```text
跑通 backend、frontend、docker core services
```

内容：

```text
FastAPI health check
Vue 基础页面
PostgreSQL
Redis
RabbitMQ
AGENTS.md
.env.example
```

---

### P1：Agent Run Mock

目标：

```text
前后端跑通一次 Agent Run
```

内容：

```text
POST /api/agent/runs
GET /api/agent/runs/{run_id}
GET /api/agent/runs/{run_id}/events
ChatPage mock
AgentRunPanel mock
```

---

### P2：Skill Registry

目标：

```text
支持 Skill 列表和显式 Skill 调用
```

内容：

```text
Skill YAML
Skill Registry
GET /api/skills
POST /api/skills/{skill_id}/run
SkillSelector
SlashCommandMenu 初版
```

---

### P3：长期记忆 V1

目标：

```text
实现记忆读写和前端管理
```

内容：

```text
agent_memories 表
MemoryManager
MemoryExtractor mock
MemoryRetriever
MemoryPage
MemoryList
```

---

### P4：基础 RAG

目标：

```text
实现文档上传和 Milvus 向量检索
```

内容：

```text
DocumentUploader
DocumentTable
文档解析
Chunk 切分
Embedding
Milvus Search
KnowledgeSourceList
```

---

### P5：RabbitMQ + Celery

目标：

```text
文档解析和 embedding 异步化
```

内容：

```text
document.ingest.queue
document.embedding.queue
tool.audit.logs.queue
Celery Worker
任务状态更新
```

---

### P6：Tool Registry

目标：

```text
统一工具调用
```

内容：

```text
ToolRegistry
ToolManager
ToolGuardrail
memory_search
hybrid_search
code_execute 占位
ToolCallTimeline
ToolApprovalDialog
```

---

### P7：DAG ReAct Runtime

目标：

```text
实现动态图 ReAct 执行
```

内容：

```text
DAGPlan
DAGValidator
TopologicalScheduler
ParallelNodeExecutor
NodeState
DAGRuntimeViewer
```

---

### P8：Harness 容错执行

目标：

```text
实现 checkpoint、retry、fallback
```

内容：

```text
RunManager
StateManager
CheckpointManager
RetryManager
FallbackManager
RunDetailPage
CheckpointList
TraceTimeline
```

---

### P9：Docker Sandbox

目标：

```text
安全执行代码
```

内容：

```text
DockerSandbox
CommandFilter
code_execute
SandboxConsole
Audit Log
```

---

### P10：Hybrid RAG + GraphRAG

目标：

```text
提升检索质量
```

内容：

```text
Elasticsearch BM25
RRF
Neo4j
Entity Extraction
Relation Extraction
GraphRAG
```

---

### P11：RAG 评测与监控

目标：

```text
补齐工程展示能力
```

内容：

```text
Golden Queries
Recall@K
MRR
NDCG
HitRate
EvalPage
MonitoringPage
Prometheus
Grafana
OpenTelemetry
```

---

## 25. Codex 实现提示词模板

每次让 Codex 实现功能时，使用以下模板：

```text
请根据 AGENTS.md 和 docs/FULLSTACK_TECH_DESIGN.md 完成本次任务。

本次只实现一个小功能，不要扩大范围。

任务目标：
【填写任务目标】

要求：
1. 先阅读相关设计文档和源码。
2. 先输出实现计划。
3. 明确会修改哪些文件。
4. 先写类型和接口，再写实现。
5. 不要引入不必要的新依赖。
6. 后端依赖必须使用 uv 管理。
7. 前端依赖必须使用 pnpm 管理。
8. 新增数据库表必须使用 Alembic migration。
9. 所有配置必须通过 .env 读取。
10. 完成后输出修改文件、运行方式和验证步骤。
```

---

## 26. 推荐第一个 Codex 任务

```text
请根据 AGENTS.md 和 docs/FULLSTACK_TECH_DESIGN.md 初始化项目骨架。

要求：
1. 创建 backend、frontend、docker、docs、scripts 目录。
2. backend 使用 uv + FastAPI。
3. frontend 使用 Vue 3 + TypeScript + Vite + pnpm。
4. docker-compose.yml 包含 PostgreSQL、Redis、RabbitMQ。
5. 创建 backend/.env.example。
6. 创建根目录 .gitignore。
7. 创建 FastAPI /health 接口。
8. 创建 Vue DashboardPage 和基础路由。
9. 保证后端、前端、中间件都能启动。
10. 输出运行命令和验证步骤。
```

---

## 27. 项目展示重点

项目完成后，展示时重点展示：

```text
1. SkillSelector 选择技术问答 Skill
2. 用户提出 Kafka 技术问题
3. Agent 创建 Run
4. 右侧 DAG Runtime 开始执行
5. Memory Retriever 命中长期记忆
6. Hybrid Retriever 返回 Milvus / BM25 / Graph 来源
7. ToolCallTimeline 展示工具调用
8. 高风险 code_execute 触发审批
9. Docker Sandbox 返回 stdout / stderr
10. RunDetailPage 展示 Checkpoint 和 Trace
11. MemoryPage 展示写入的长期记忆
12. EvalPage 展示 RAG 指标
13. MonitoringPage 展示 token 成本和任务成功率
```

---

## 28. 简历描述

项目名称：

```text
Paris Agent：面向程序员技术学习场景的 Skill-based Agent Workbench
```

项目描述：

```text
基于 Python、FastAPI、LangGraph、PostgreSQL、Milvus、RabbitMQ、Elasticsearch、Neo4j、Docker 和 Vue3 构建面向程序员技术学习场景的 Skill-based Agent Workbench。系统支持 Skill-based Agent Workflow、自研长期记忆系统、Hybrid GraphRAG、动态图 ReAct Runtime、Agent Harness 容错执行、多层安全校验、代码沙箱执行、RAG 评测和可观测性追踪，帮助用户完成技术问答、学习路线规划、文档知识沉淀、代码执行验证和个人知识体系构建。
```

技术亮点：

```text
1. 设计 Skill Registry 与 Skill Router，将技术问答、学习路线、RAG 评测、代码沙箱、记忆整理等能力封装为可配置 Skill。
2. 设计自研长期记忆系统，支持学习画像、项目记忆、事件记忆、程序性记忆和运行时记忆。
3. 设计动态图 ReAct Runtime，将复杂任务建模为 DAG，支持并行执行、节点重试、fallback 和 checkpoint。
4. 设计 Agent Harness 容错执行引擎，统一管理状态、工具、超时、重试、恢复和 Trace。
5. 设计 Hybrid GraphRAG，融合 Milvus 向量检索、Elasticsearch BM25 和 Neo4j 图谱检索。
6. 设计多层安全机制和 Docker Sandbox，降低工具调用和代码执行风险。
7. 使用 RabbitMQ + Celery 实现文档解析、Embedding、工具审计和评测任务异步化。
8. 前端实现 Agent Workbench，可视化展示 Skill、DAG Runtime、Tool Calls、Memories、Trace、Checkpoint 和 RAG 来源。
```
