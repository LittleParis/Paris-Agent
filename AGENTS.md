# AGENTS.md

## 1. 项目定位

本项目名为 Paris Agent，是一个面向程序员技术学习场景的 Skill-based Agent Workbench。

项目核心目标不是做普通聊天机器人，而是实现一个具备以下能力的 Agent 工程系统：

1. Skill-based Agent Workflow
2. 自研长期记忆系统
3. Hybrid GraphRAG
4. 动态图 ReAct Runtime
5. Agent Harness 容错执行引擎
6. 多层安全校验与 Docker Sandbox
7. RabbitMQ 异步任务队列
8. 前端 Agent Runtime 可视化
9. RAG 评测与可观测性

所有开发任务必须围绕以上目标展开，不要偏离为普通 ChatBot 项目。

---

## 2. 技术栈约束

### 2.1 后端

后端技术栈固定为：

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
```

后端依赖管理固定使用：

```text
uv + pyproject.toml + uv.lock
```

禁止使用：

```text
pip install
pip freeze
requirements.txt 作为主依赖管理方式
```

新增后端依赖必须使用：

```bash
uv add package_name
```

新增开发依赖必须使用：

```bash
uv add --dev package_name
```

安装环境必须使用：

```bash
uv sync
```

运行后端必须使用：

```bash
uv run uvicorn app.main:app --reload
```

---

### 2.2 前端

前端技术栈固定为：

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

前端依赖管理固定使用：

```text
pnpm + package.json + pnpm-lock.yaml
```

禁止混用：

```text
npm
yarn
pnpm
```

本项目只允许使用 pnpm。

新增前端依赖必须使用：

```bash
pnpm add package_name
```

新增前端开发依赖必须使用：

```bash
pnpm add -D package_name
```

运行前端必须使用：

```bash
pnpm dev
```

---

### 2.3 中间件

中间件统一使用 Docker Compose 管理。

第一阶段只启动核心中间件：

```text
PostgreSQL
Redis
RabbitMQ
```

第二阶段再接入：

```text
Milvus
Elasticsearch
Neo4j
```

第三阶段再接入：

```text
Prometheus
Grafana
OpenTelemetry Collector
```

不要一开始就把所有中间件全部接入。

---

## 3. 项目目录约束

项目根目录必须保持如下结构：

```text
paris-agent/
├── backend/
│   ├── app/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── .env.example
│   └── README.md
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── README.md
├── docker/
│   ├── docker-compose.yml
│   └── .env.example
├── docs/
│   └── FULLSTACK_TECH_DESIGN.md
├── scripts/
├── AGENTS.md
├── .gitignore
└── README.md
```

不要随意改变顶层目录结构。

---

## 4. 后端目录规范

后端核心目录必须保持如下结构：

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── schemas/
│   ├── agent/
│   ├── skills/
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
└── .env.example
```

各模块职责如下：

```text
api：FastAPI 路由
core：配置、日志、安全、异常处理
db：数据库连接、模型、Repository
schemas：Pydantic 请求响应模型
agent：LangGraph、AgentState、DAG Runtime、Harness
skills：Skill Registry、Skill Router、Skill Executor
memory：长期记忆系统
rag：文档解析、向量检索、BM25、GraphRAG
tools：Tool Registry、Tool Manager、Sandbox Tool
security：Input Guardrail、Output Guardrail、权限与风险检查
queue：Celery、RabbitMQ 任务和事件
eval：RAG 评测
observability：Trace、Metrics、Cost Tracker
```

---

## 5. 前端目录规范

前端核心目录必须保持如下结构：

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

前端页面至少包括：

```text
/dashboard
/chat
/knowledge/documents
/knowledge/chunks
/memory
/skills
/tools
/tools/audit
/runs
/runs/:runId
/eval
/sandbox
/monitoring
/settings
```

---

## 6. 开发方式

每次只实现一个小功能，不允许一次性生成整个系统。

每次任务必须遵守如下流程：

```text
1. 先阅读 docs/FULLSTACK_TECH_DESIGN.md
2. 再阅读当前相关源码文件
3. 输出实现计划
4. 明确要修改哪些文件
5. 先写类型定义和接口
6. 再写具体实现
7. 补充基础测试或手动验证步骤
8. 保证项目可运行
9. 输出变更总结
```

禁止：

```text
1. 一次性大规模改动
2. 随意引入新依赖
3. 硬编码 API Key、数据库密码、模型密钥
4. 绕过 .env 读取配置
5. 直接修改数据库而不写 Alembic migration
6. 修改 lock 文件而不说明原因
7. 修改项目目录结构而不说明原因
8. 删除已有功能而不说明影响
```

---

## 7. 环境变量规则

所有配置必须通过 `.env` 读取。

必须提交：

```text
.env.example
```

禁止提交：

```text
.env
```

禁止把以下内容写死到代码中：

```text
数据库密码
RabbitMQ 密码
Redis 地址
OpenAI API Key
模型 API Key
JWT Secret
第三方服务 Token
```

后端读取配置必须通过：

```text
pydantic-settings
```

---

## 8. 数据库规则

数据库使用：

```text
PostgreSQL + SQLAlchemy + Alembic
```

新增表必须：

```text
1. 修改 SQLAlchemy model
2. 生成 Alembic migration
3. 检查 migration 内容
4. 执行 upgrade
```

禁止手动进入数据库直接改表。

核心表包括：

```text
agent_runs
agent_steps
agent_node_states
agent_tool_calls
agent_checkpoints
agent_memories
agent_skills
agent_skill_runs
documents
document_chunks
knowledge_entities
knowledge_relations
audit_logs
runtime_events
```

---

## 9. Agent Runtime 规则

Agent Runtime 必须基于 LangGraph 和自研 Harness 设计。

核心模块包括：

```text
AgentState
DAGPlan
DAGValidator
TopologicalScheduler
ReActNodeExecutor
RunManager
StateManager
CheckpointManager
RetryManager
FallbackManager
TimeoutManager
ToolIsolationManager
TraceRecorder
```

Agent 不允许直接调用外部工具，必须通过 Tool Manager。

Agent 执行流程：

```text
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
```

---

## 10. Skill 规则

本项目必须支持 Skill-based Agent Workflow。

Skill 是能力包，必须包含：

```text
Skill ID
Name
Description
Version
Input Schema
Output Schema
Prompt
Tools
Workflow
Memory Policy
Safety Policy
Runtime Config
```

Skill 配置使用 YAML，放在：

```text
backend/app/skills/definitions/
```

第一阶段至少实现：

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

Skill 不允许直接调用工具，必须通过 Skill Executor 转换为 DAG Plan，再交给 Agent Harness 执行。

---

## 11. 记忆系统规则

长期记忆系统必须自研，不允许只保存聊天记录。

记忆类型包括：

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

记忆写入流程：

```text
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
Deduplication
↓
Merge / Update
↓
PostgreSQL + Milvus
```

记忆检索必须综合：

```text
similarity
importance
recency
access_count
project_relevance
```

---

## 12. RAG 规则

RAG 分阶段实现。

第一阶段：

```text
文档上传
文档解析
Chunk 切分
Embedding
Milvus 向量检索
引用来源返回
```

第二阶段：

```text
Elasticsearch BM25
Milvus + BM25 双路召回
RRF 融合排序
```

第三阶段：

```text
Neo4j 技术知识图谱
GraphRAG
Memory Graph
```

回答技术问题时必须尽量返回来源，不允许编造来源。

---

## 13. 工具调用规则

所有工具必须注册到 Tool Registry。

工具必须声明：

```text
name
description
input_schema
output_schema
risk_level
requires_approval
enabled
```

风险等级：

```text
safe：查询类工具
low：记忆写入、文档生成
medium：任务创建、项目更新
high：代码执行、Shell 执行
block：删除文件、访问宿主机、危险命令
```

高风险工具必须经过 Tool Guardrail。

代码执行必须进入 Docker Sandbox。

---

## 14. 安全规则

系统必须实现多层安全校验：

```text
Input Guardrail
Intent Risk Classifier
Tool Risk Classifier
Permission Checker
Docker Sandbox
Output Guardrail
Audit Logger
```

禁止绕过安全层直接调用工具。

Shell 命令默认不开放。

危险命令必须拦截：

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

## 15. RabbitMQ / Celery 规则

RabbitMQ 用于异步任务和审计事件。

核心队列：

```text
document.ingest.queue
document.embedding.queue
agent.run.events.queue
tool.audit.logs.queue
rag.eval.tasks.queue
cost.usage.events.queue
sandbox.exec.queue
```

Celery 任务放在：

```text
backend/app/queue/
```

每个任务必须：

```text
1. 有明确输入 schema
2. 有错误处理
3. 更新任务状态
4. 记录日志
```

---

## 16. 前端实现规则

前端不是普通聊天框，而是 Agent Workbench。

ChatPage 必须包含：

```text
左侧：会话 / 项目 / Skill 列表
中间：聊天消息
右侧：Agent Runtime 面板
```

右侧面板必须展示：

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

前端必须支持：

```text
SkillSelector
SlashCommandMenu
SkillRunPanel
DAGRuntimeViewer
ToolCallTimeline
MemoryList
KnowledgeSourceList
SandboxConsole
TraceTimeline
MetricCard
```

---

## 17. API 规则

所有 API 路由必须放在：

```text
backend/app/api/
```

所有请求响应模型必须放在：

```text
backend/app/schemas/
```

前端 API client 必须放在：

```text
frontend/src/api/
```

API 命名必须清晰，不要在页面组件里直接写请求 URL。

---

## 18. 测试与验证规则

后端至少提供：

```text
health check
基础 API 测试
记忆系统测试
Skill Registry 测试
Tool Registry 测试
```

前端至少提供手动验证步骤。

每次任务完成必须输出：

```text
修改文件
实现内容
运行命令
验证方式
已知问题
```

---

## 19. 推荐实现顺序

必须按以下顺序推进：

```text
P0：项目骨架
P1：后端 health check + 前端基础布局
P2：Agent Run mock
P3：ChatPage mock
P4：SSE 事件流
P5：Skill Registry
P6：长期记忆 V1
P7：文档上传 + 基础 RAG
P8：RabbitMQ + Celery
P9：Tool Registry
P10：DAG ReAct Runtime
P11：Harness Checkpoint / Retry / Fallback
P12：Docker Sandbox
P13：Hybrid RAG
P14：GraphRAG
P15：RAG 评测
P16：监控与可观测性
```

不要跳过前面的基础阶段直接实现复杂功能。

---

## 20. Codex 执行任务模板

每次执行任务时，先按以下格式输出计划：

```text
任务目标：
相关文档：
需要修改的文件：
实现步骤：
数据结构：
接口设计：
测试或验证方式：
风险点：
```

完成后输出：

```text
完成内容：
修改文件：
运行方式：
验证结果：
后续建议：
```
