# Paris Agent 数据库演进策略

## 1. 文档目的

本文定义 Paris Agent 从当前 `agent_runs` 单表基线演进到完整 Agent Workbench 数据模型
的顺序、约束和验收规则。

本文不是一次性建表清单。每张表只能在对应 P0-P16 阶段通过专项设计、SQLAlchemy
Model 和 Alembic Migration 引入。

权威层级：

```text
AGENTS.md
↓
FULLSTACK_TECH_DESIGN.md
↓
本数据库演进策略与阶段专项表设计
↓
SQLAlchemy Model / Alembic Migration / 数据库测试
```

---

## 2. 当前数据库基线

### 2.1 已实现 Migration

```text
backend/alembic/versions/20260613_0001_create_agent_runs.py
Revision: 20260613_0001
```

该 Migration 对应当前 `AGENTS.md` 的 P2 Agent Run Mock。历史注释中出现的 P1 表述
属于旧阶段命名，不能用于后续需求编号。

### 2.2 已实现 agent_runs

当前表已经具备：

- `BIGINT GENERATED ALWAYS AS IDENTITY` 内部主键。
- UUID `run_id` 对外业务标识和唯一约束。
- UUID `thread_id`、`user_id`、`project_id` 预留关联字段。
- `task_type`、`status`、`input`、token、成本和时间字段的合理 NOT NULL。
- `queued`、`running`、`succeeded`、`failed`、`cancelled`、
  `waiting_approval` 状态 CHECK。
- 非空白 input CHECK。
- token 和成本非负 CHECK。
- `TIMESTAMPTZ` 语义的时间字段。
- `NUMERIC(18,8)` 成本字段。
- user、thread、project 和活跃状态访问路径索引。

该表是后续演进基线。除非发现实际缺陷并通过专项迁移修复，后续任务不得重建、
重命名或破坏其现有 API 契约。

### 2.3 当前已知演进点

以下内容尚未在 P2 实现：

- users、projects、threads 等父表和真实外键。
- 数据库层状态迁移保护或乐观锁。
- runtime_events 持久化。
- 节点、工具调用和 Checkpoint 子表。
- Skill Version、Memory、Knowledge、Audit 和 Eval 表。
- 多租户 Row-Level Security。

这些是后续阶段任务，不是当前 Migration 错误。

---

## 3. 全局建模规范

### 3.1 标识策略

```text
内部主键：BIGINT GENERATED ALWAYS AS IDENTITY
外部业务 ID：UUID
固定配置标识：受格式和长度约束的 TEXT
```

使用双标识时：

- API 和事件暴露 UUID，不暴露内部自增 ID。
- 表间关联优先使用内部主键以提高 Join 效率，或统一使用业务 UUID。
- 同一领域关系必须采用一致策略，不能部分引用 `id`、部分引用 UUID 而无明确原因。
- 引用业务 UUID 时，被引用列必须有 UNIQUE 约束。

禁止新表使用：

```text
BIGSERIAL
字符串模拟 UUID
可预测的对外自增 ID
```

### 3.2 字符串

- 默认使用 `TEXT`。
- 业务长度限制使用 `CHECK (length(column) <= n)`。
- 非空白要求使用 `CHECK (length(btrim(column)) > 0)`。
- 不使用 `CHAR(n)`。
- 不因为性能误区默认使用 `VARCHAR(n)`。

### 3.3 时间

所有业务时间使用：

```sql
TIMESTAMPTZ NOT NULL
```

创建时间通常使用：

```sql
DEFAULT now()
```

字段语义必须区分：

```text
created_at
updated_at
started_at
ended_at
completed_at
last_accessed_at
expires_at
last_synced_at
```

`updated_at` 当前由 SQLAlchemy `onupdate` 维护。进入多 Worker 写入前，必须评估数据库
触发器或显式 Repository 更新时间，以避免绕过 ORM 的更新不刷新时间。

### 3.4 数值

```text
成本：NUMERIC(18,8)
评分：DOUBLE PRECISION 或明确精度的 NUMERIC
token/累计计数：BIGINT
常规索引、重试次数、毫秒延迟：INTEGER
```

必须增加范围约束：

```text
total_tokens >= 0
total_cost >= 0
retry_count >= 0
access_count >= 0
chunk_count >= 0
step_index >= 0
chunk_index >= 0
latency_ms >= 0
importance BETWEEN 0 AND 1
confidence BETWEEN 0 AND 1
version >= 1
```

禁止用浮点类型保存金额。

### 3.5 状态

会持续演进的业务状态使用 `TEXT + CHECK`，不默认使用 PostgreSQL ENUM。

每个状态字段必须同时定义：

- 允许值。
- 初始状态。
- 合法迁移。
- 终态。
- 失败和取消语义。

Agent Run 状态固定为：

```text
queued
running
waiting_approval
succeeded
failed
cancelled
```

### 3.6 JSONB 和数组

JSONB 适合：

```text
配置快照
输入/输出快照
状态快照
可扩展事件 payload
审计 detail
```

核心关联、高频过滤字段和状态不能藏在 JSONB 中。

JSONB 应使用默认值和类型约束：

```sql
payload JSONB NOT NULL DEFAULT '{}'::jsonb
CHECK (jsonb_typeof(payload) = 'object')
```

只有存在实际 `@>` 或 key 查询时才添加 GIN 索引。

简单有序 ID 列表可以使用 `TEXT[]` 或 `UUID[]`。如果元素需要独立约束、状态或关联，
必须使用关系表。

---

## 4. 关系完整性规则

每个外键必须明确：

```text
被引用列
ON DELETE 行为
ON UPDATE 行为
是否允许 NULL
是否需要 DEFERRABLE
对应显式索引
```

PostgreSQL 不会自动为外键列建立索引。高频 Join、父表删除检查和 API 过滤使用的外键
必须显式索引。

删除策略原则：

```text
CASCADE
  父资源删除后没有独立保留价值的纯子记录

RESTRICT
  历史、账务、审计或仍被运行记录引用的版本

SET NULL
  历史记录必须保留，但父资源可以删除或匿名化
```

审计记录默认不可由普通业务 API 更新或删除。

---

## 5. 分阶段表设计顺序

### 5.1 P2：agent_runs

**状态：** 已实现。

后续可通过增量 Migration 增加：

- `parent_run_id`：整个 Run 重试或派生关系。
- 乐观锁版本列：多 Worker 并发状态更新。
- 父表建立后增加 user、project、thread 外键。

这些字段必须在真实访问路径出现后再设计，不提前加入。

### 5.2 P4：runtime_events

用途：SSE 持久回放、断线恢复和 Run Timeline。

推荐字段：

```text
id                  BIGINT IDENTITY PK
event_id            UUID UNIQUE NOT NULL
run_id              UUID NOT NULL FK
sequence            BIGINT NOT NULL
event_type          TEXT NOT NULL
status              TEXT NOT NULL
payload             JSONB NOT NULL DEFAULT {}
created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

约束与索引：

```text
UNIQUE (run_id, sequence)
CHECK sequence > 0
INDEX (run_id, sequence)
INDEX (created_at) 仅在保留/清理任务需要时添加
```

事件是追加写数据，不允许普通业务更新。

### 5.3 Identity、Project 和 Conversation

这些父领域必须在真实多用户、项目和会话持久化前引入。

```text
users
projects
project_members
chat_threads
chat_messages
```

关键关系：

```text
projects.owner_user_id -> users
project_members.project_id -> projects
project_members.user_id -> users
chat_threads.user_id -> users
chat_threads.project_id -> projects
chat_messages.thread_id -> chat_threads
agent_runs.user_id -> users
agent_runs.project_id -> projects
agent_runs.thread_id -> chat_threads
```

需要先确定账户删除、项目删除、聊天保留和匿名化策略，再选择 CASCADE、RESTRICT 或
SET NULL。

### 5.4 P5：Skill 版本模型

推荐拆分：

```text
agent_skills
  id
  skill_id
  name
  description
  enabled
  created_at
  updated_at

agent_skill_versions
  id
  skill_id FK
  version
  config
  config_hash
  created_at

agent_skill_runs
  skill_run_id
  run_id FK
  skill_version_id FK
  input
  output
  status
  error_message
  created_at
  updated_at
```

约束：

```text
UNIQUE agent_skills(skill_id)
UNIQUE agent_skill_versions(skill_id, version)
UNIQUE agent_skill_versions(skill_id, config_hash) 可按发布策略评估
```

Skill Version 一旦被 Run 引用即不可修改。

### 5.5 P6：agent_memories

最低字段：

```text
memory_id
user_id
project_id
memory_type
content
summary
importance
confidence
source_type
source_id
tags
external_vector_id
embedding_version
sync_status
version
access_count
last_accessed_at
created_at
updated_at
expires_at
```

重点索引：

```text
(user_id, memory_type, updated_at DESC)
(project_id, updated_at DESC) WHERE project_id IS NOT NULL
tags GIN 仅在实际标签包含查询出现时添加
```

记忆内容删除时必须同步删除或失效 Milvus 投影。

### 5.6 P7：documents 和 document_chunks

关键关系：

```text
document_chunks.document_id -> documents
ON DELETE CASCADE
```

组合唯一约束：

```text
UNIQUE (document_id, chunk_index)
```

外部索引同步字段：

```text
milvus_id
elastic_id
embedding_version
index_version
sync_status
last_synced_at
sync_error
```

不能只保存外部 ID 而不记录同步状态。

### 5.7 P9：agent_tool_calls 和 audit_logs

`agent_tool_calls` 保存一次工具调用的业务状态：

```text
tool_call_id
run_id
node_id
tool_name
input
output
status
risk_level
requires_approval
approved_by
approved_at
latency_ms
created_at
updated_at
```

`audit_logs` 保存不可变安全和操作事实：

```text
audit_id
run_id
user_id
tool_call_id
event_type
risk_level
input_hash
status
sandbox_enabled
detail
created_at
```

工具调用删除不能导致审计日志丢失。优先使用 RESTRICT 或 SET NULL，并保留去标识化
审计信息。

### 5.8 P10：agent_node_states

最低约束：

```text
UNIQUE (run_id, node_id)
retry_count >= 0
ended_at >= started_at
```

访问路径：

```text
(run_id, created_at/node order)
(run_id, status)
```

`agent_steps` 暂不创建。只有明确它用于跨节点的 ReAct step，而非复制 node state 时，
才单独设计：

```text
UNIQUE (run_id, step_index)
```

### 5.9 P11：agent_checkpoints

Checkpoint 必须关联：

```text
checkpoint_id
run_id
node_id
state_schema_version
state_snapshot
next_nodes
created_at
```

状态快照需要 Schema Version，确保代码升级后可以识别、迁移或拒绝旧 Checkpoint。

### 5.10 P15：RAG Eval

```text
rag_eval_tasks
rag_eval_results
golden_datasets
golden_queries
```

必须保存：

- 数据集和 Query 版本。
- 检索策略及完整参数。
- 知识索引版本。
- 指标结果。
- 模型与 Prompt 版本。
- 错误信息、开始和完成时间。

这样同一份报告才能复现。

---

## 6. 推荐访问路径

只为实际查询添加索引。当前优先访问路径：

```text
agent_runs (user_id, created_at DESC)
agent_runs (thread_id, created_at DESC)
agent_runs (project_id, created_at DESC)
agent_runs active partial (status, created_at)

runtime_events UNIQUE (run_id, sequence)
runtime_events (run_id, sequence)

agent_skill_versions UNIQUE (skill_id, version)
agent_skill_runs (run_id)
agent_skill_runs (skill_version_id, created_at DESC)

agent_memories (user_id, memory_type, updated_at DESC)
agent_memories (project_id, updated_at DESC)

documents (user_id, created_at DESC)
documents (status, updated_at)
document_chunks UNIQUE (document_id, chunk_index)

agent_tool_calls (run_id, created_at)
agent_tool_calls (status, created_at) WHERE status IN active states
audit_logs (run_id, created_at)
audit_logs (user_id, created_at DESC)

agent_node_states UNIQUE (run_id, node_id)
agent_checkpoints (run_id, created_at DESC)
```

索引设计必须用真实 SQL 和 `EXPLAIN (ANALYZE, BUFFERS)` 验证，不能只按字段数量堆索引。

---

## 7. 多存储同步

### 7.1 所有权

```text
PostgreSQL      业务事实和同步事实
Milvus          向量投影
Elasticsearch   文本检索投影
Neo4j           图关系投影
```

### 7.2 同步状态

推荐值：

```text
pending
syncing
succeeded
failed
deleting
deleted
```

同步任务必须携带：

```text
source_record_id
target_store
index_version
idempotency_key
attempt
```

外部写入成功但 PostgreSQL 状态更新失败时，消费者重试必须是幂等的。

### 7.3 删除

删除业务资源时：

1. PostgreSQL 先记录删除意图或软删除状态。
2. Outbox 发布外部索引删除任务。
3. Worker 幂等删除外部投影。
4. 更新同步状态。
5. 保留失败重试和人工补偿入口。

不能在单个 HTTP 请求中依赖对多个存储的分布式事务。

---

## 8. 多租户与安全

接入真实用户后：

- 所有用户资源查询必须包含 `user_id` 或项目成员授权条件。
- Repository 不能只按业务 UUID 查询后再由页面判断归属。
- 审计表避免保存明文秘密、完整代码密钥和无必要的个人数据。
- 评估 Row-Level Security 作为数据库纵深防御。
- RLS 不替代 FastAPI 应用层授权和测试。

数据保留策略至少覆盖：

```text
聊天和 Run
Runtime Event
Checkpoint
Tool Input/Output
Audit Log
原始文档
Memory
Eval Result
```

---

## 9. Alembic 实施流程

每次结构变更必须执行：

1. 阅读阶段专项契约和现有 Migration。
2. 修改 SQLAlchemy Model。
3. 使用 Alembic 生成候选 Migration。
4. 人工检查类型、默认值、约束、索引、外键和删除顺序。
5. 在空数据库执行 `upgrade head`。
6. 在含代表性数据的数据库验证兼容性。
7. 执行 `downgrade -1`。
8. 再次执行 `upgrade head`。
9. 运行 Repository、API 和集成测试。
10. 对关键查询执行查询计划检查。

Windows PowerShell 命令：

```powershell
Set-Location backend
uv run alembic current
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run pytest
```

生产大表迁移还必须评估：

- 是否重写整表。
- 锁持续时间。
- 是否需要先 nullable、回填、再 NOT NULL。
- 是否需要 `CREATE INDEX CONCURRENTLY`。
- Migration 事务边界。
- 回滚是否会丢失新数据。

---

## 10. 每张新表的审查模板

```text
业务目的：
所属阶段：
数据所有者：
主键和业务 ID：
必填字段：
状态与状态迁移：
唯一约束：
CHECK：
外键：
ON DELETE：
外键索引：
API 查询索引：
JSONB 使用理由：
数据保留与删除：
多租户授权条件：
外部存储同步：
upgrade：
downgrade：
自动测试：
查询计划：
```

缺少以上关键项时，不应生成正式 Migration。

---

## 11. 验收清单

数据库专项任务完成前必须确认：

```text
[ ] 没有使用 BIGSERIAL
[ ] 没有使用无时区 TIMESTAMP
[ ] 金额没有使用浮点类型
[ ] 必填字段均有 NOT NULL
[ ] 默认值同时考虑 ORM 和数据库写入
[ ] 状态和数值范围有 CHECK
[ ] 唯一业务规则有 UNIQUE
[ ] 每个外键有删除策略
[ ] 高频外键有显式索引
[ ] 组合索引与实际查询顺序一致
[ ] JSONB 没有承载核心关系
[ ] 多存储投影可以重建
[ ] Migration upgrade 和 downgrade 均通过
[ ] 自动测试从空库可重建 schema
[ ] 没有绕过 Alembic 手工改表
```

---

## 12. 下一步数据库需求顺序

```text
1. 保持 agent_runs 基线稳定
2. P4 设计并实现 runtime_events
3. 在需要真实会话前设计 users/projects/chat_threads/chat_messages
4. P5 实现 Skill 和不可变 Skill Version
5. P6 实现 Memory
6. P7 实现 Documents 和 Chunks
7. P9 实现 Tool Calls 和 Audit Logs
8. P10 实现 Node States
9. P11 实现 Checkpoints
10. P15 实现 Eval 数据集、任务和结果
11. 数据量和查询证据充分后再考虑分区、归档或反规范化
```
