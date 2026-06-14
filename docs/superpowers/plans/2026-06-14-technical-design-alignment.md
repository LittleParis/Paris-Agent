# Paris Agent Technical Design Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Paris Agent 的总体技术设计、P1 Agent Run 契约和数据库修订策略统一为与 `AGENTS.md` 及当前 P1 实现一致的可执行文档基线。

**Architecture:** `AGENTS.md` 保持最高约束，`FULLSTACK_TECH_DESIGN.md` 负责跨阶段架构和统一契约，专项文档负责阶段细节。文档明确区分“当前已实现”“当前阶段目标”“未来设计”，并通过状态、字段、阶段编号和 PostgreSQL 规则扫描防止契约漂移。

**Tech Stack:** Markdown、FastAPI/Pydantic/OpenAPI 契约、PostgreSQL/SQLAlchemy/Alembic 设计规则、Vue 3 前端架构、PowerShell 验证命令。

---

## File Map

- Modify: `docs/FULLSTACK_TECH_DESIGN.md`
  - 总体架构、统一技术契约、当前实现基线和 P0-P16 需求菜单。
- Modify: `docs/P1_AGENT_RUN_CONTRACT.md`
  - 与当前 Model、Schema、路由、Mock Runner 和 SSE 实现保持一致。
- Modify: `docs/DATABASE_SCHEMA_REVISION_STRATEGY.md`
  - 数据库目标模型、阶段顺序、约束、外键、索引和 Migration 验收规则。
- Reference only: `AGENTS.md`
  - 项目约束和 P0-P16 阶段顺序，不在无直接矛盾时修改。
- Reference only: `backend/app/db/models/agent_run.py`
- Reference only: `backend/app/schemas/agent.py`
- Reference only: `backend/app/api/routes_agent.py`
- Reference only: `backend/app/agent/events.py`
- Reference only: `backend/app/agent/mock_runner.py`
- Reference only: `backend/alembic/versions/*.py`

### Task 1: 重构总体技术设计基线

**Files:**
- Modify: `docs/FULLSTACK_TECH_DESIGN.md`
- Reference: `AGENTS.md`
- Reference: `docs/superpowers/specs/2026-06-14-technical-design-alignment-design.md`

- [ ] **Step 1: 写入文档权威层级和状态标记**

在文档开头明确：

```text
AGENTS.md > FULLSTACK_TECH_DESIGN.md > 专项契约 > 已实现代码与 Migration
```

同时定义：

```text
[已实现]
[进行中]
[目标设计]
[阶段外]
```

要求所有未来能力不能写成当前已经可用。

- [ ] **Step 2: 写入当前实现基线**

记录当前事实：

```text
P0 项目骨架已完成
P1 后端 Agent Run Mock 已完成
P1 前端 ChatPage 联调进行中
P2-P16 未开始
```

列出当前已存在的 POST、GET 和 SSE 接口，以及进程内 Mock Runner 的限制。

- [ ] **Step 3: 重构模块边界**

明确以下职责：

```text
LangGraph：高层状态图、暂停恢复入口、Checkpoint 集成
DAG Runtime：计划校验、依赖解析、拓扑调度、并行节点执行
Agent Harness：Run 生命周期、超时、重试、Fallback、事件、Trace、成本
Skill Executor：Skill 输入转换为已验证执行计划
Tool Manager：权限、风险、审批、执行、审计的唯一入口
```

补充模块化单体的依赖方向，禁止路由层长期承载业务编排。

- [ ] **Step 4: 统一跨模块技术契约**

写入以下不可变规则：

```text
外部业务 ID 使用 UUID
固定配置键使用受约束 TEXT
时间使用 TIMESTAMPTZ
成本使用 NUMERIC(18,8)
Agent Run 成功状态使用 succeeded
API 错误使用 Problem Details
列表接口使用游标分页
可重试创建支持 Idempotency-Key
```

- [ ] **Step 5: 重写数据库、API、SSE 和消息章节**

数据库章节记录领域表、关系、约束和访问路径，不保留可被误认为可直接执行的旧概念 SQL。

SSE 章节必须定义：

```text
sequence
Last-Event-ID
心跳
去重
终止事件
runtime_events 持久化
```

RabbitMQ 章节必须定义消息信封、ACK、重试、DLQ、幂等和 Transactional Outbox。

- [ ] **Step 6: 写入 P0-P16 分步需求菜单**

阶段名称和顺序逐字对齐 `AGENTS.md`。每阶段必须包含：

```text
状态
目标
前置依赖
后端
前端
数据库/Migration
接口/事件/消息
测试与验证
完成标准
本阶段不做
```

- [ ] **Step 7: 检查主文档格式**

Run:

```powershell
git diff --check -- docs/FULLSTACK_TECH_DESIGN.md
```

Expected: 无输出，退出码为 `0`。

- [ ] **Step 8: 提交主设计文档**

```powershell
git add -- docs/FULLSTACK_TECH_DESIGN.md
git commit -m "docs: align fullstack technical design"
```

### Task 2: 对齐 P1 Agent Run 契约

**Files:**
- Modify: `docs/P1_AGENT_RUN_CONTRACT.md`
- Reference: `backend/app/db/models/agent_run.py`
- Reference: `backend/app/schemas/agent.py`
- Reference: `backend/app/api/routes_agent.py`
- Reference: `backend/app/agent/events.py`
- Reference: `backend/app/agent/mock_runner.py`

- [ ] **Step 1: 对齐 Run 状态和状态迁移**

文档只允许：

```text
queued
running
waiting_approval
succeeded
failed
cancelled
```

P1 实际迁移记录为：

```text
queued -> running -> succeeded
queued -> running -> failed
```

- [ ] **Step 2: 对齐 REST 请求和响应**

逐字段核对：

```text
AgentRunCreate
AgentRunCreated
AgentRunRead
```

明确 `POST` 返回 `202 Accepted`、`Location`、`detail_url` 和 `events_url`；
`user_id` 来自服务端配置，客户端不能提交。

- [ ] **Step 3: 对齐 SSE 帧和 P1 限制**

记录当前事件顺序：

```text
run.started
node.started
message.delta
message.delta
node.completed
run.completed
```

记录 `id`、`event`、`data` 三个 SSE 字段，并明确当前 Broker 不支持服务重启恢复、
多实例共享、持久事件回放和 `Last-Event-ID`。

- [ ] **Step 4: 增加后续兼容迁移说明**

明确未来 `runtime_events` 稳定信封不能直接破坏 P1 前端，必须提供兼容映射或同步升级
专项契约。

- [ ] **Step 5: 对比源码字段**

Run:

```powershell
Select-String -Path 'docs\P1_AGENT_RUN_CONTRACT.md' -Pattern 'success','succeeded','run.started','message.delta','Location','202 Accepted'
```

Expected: `success` 不作为状态值出现；其余契约关键词均存在。

- [ ] **Step 6: 提交 P1 契约**

```powershell
git add -- docs/P1_AGENT_RUN_CONTRACT.md
git commit -m "docs: synchronize p1 agent run contract"
```

### Task 3: 更新数据库修订策略

**Files:**
- Modify: `docs/DATABASE_SCHEMA_REVISION_STRATEGY.md`
- Reference: `docs/FULLSTACK_TECH_DESIGN.md`
- Reference: `backend/app/db/models/agent_run.py`
- Reference: `backend/alembic/versions/*.py`

- [ ] **Step 1: 标记 agent_runs 已实现基线**

记录已实现内容：

```text
BIGINT IDENTITY 内部主键
UUID run_id
NOT NULL 与默认值
状态和非负 CHECK
TIMESTAMPTZ
NUMERIC(18,8)
用户、线程、项目和活跃状态索引
```

后续策略不能要求重新设计或破坏该 P1 契约。

- [ ] **Step 2: 确定基础领域表顺序**

按以下依赖实现：

```text
users
projects / project_members
chat_threads / chat_messages
agent runtime 子表
skills / skill versions
memories
documents / chunks
audit logs
evaluation
```

`agent_steps` 标记为待明确用途，不能与 `agent_node_states` 重复创建。

- [ ] **Step 3: 补齐关系、约束和索引规则**

为每个未来表要求：

```text
NOT NULL
DEFAULT
CHECK
UNIQUE
FOREIGN KEY
ON DELETE
FK INDEX
API access-path index
retention policy
```

明确 Skill 版本不可变，运行记录必须引用实际执行版本。

- [ ] **Step 4: 补齐多存储同步模型**

PostgreSQL 元数据至少保存：

```text
external_id
sync_status
index_version
last_synced_at
sync_error
```

明确 Milvus、Elasticsearch 和 Neo4j 都是可重建投影。

- [ ] **Step 5: 写入 Migration 验收流程**

固定顺序：

```text
修改 Model
生成 Migration
人工检查 upgrade/downgrade
执行 upgrade
执行 downgrade
重新 upgrade
运行测试
检查常用查询计划
```

- [ ] **Step 6: 提交数据库策略**

```powershell
git add -- docs/DATABASE_SCHEMA_REVISION_STRATEGY.md
git commit -m "docs: refine database evolution strategy"
```

### Task 4: 执行跨文档一致性验证

**Files:**
- Verify: `AGENTS.md`
- Verify: `docs/FULLSTACK_TECH_DESIGN.md`
- Verify: `docs/P1_AGENT_RUN_CONTRACT.md`
- Verify: `docs/DATABASE_SCHEMA_REVISION_STRATEGY.md`

- [ ] **Step 1: 检查旧品牌**

Run:

```powershell
Get-ChildItem -Path 'docs' -Recurse -File |
  Select-String -Pattern 'AGI Assistant','agi-assistant' -CaseSensitive:$false
```

Expected: 无匹配。

- [ ] **Step 2: 检查状态冲突**

Run:

```powershell
Get-ChildItem -Path 'docs' -Recurse -File |
  Select-String -Pattern "'success'","status: success","status = success"
```

Expected: 主契约中无 `success` 状态；说明性“成功”文字不受限制。

- [ ] **Step 3: 检查旧 PostgreSQL 写法**

Run:

```powershell
Select-String -Path 'docs\FULLSTACK_TECH_DESIGN.md' `
  -Pattern 'BIGSERIAL','VARCHAR\(','TIMESTAMP(?!TZ)'
```

Expected: 只允许在“禁止使用”或历史问题说明中出现。

- [ ] **Step 4: 核对 P0-P16**

Run:

```powershell
Select-String -Path 'AGENTS.md','docs\FULLSTACK_TECH_DESIGN.md' `
  -Pattern '^P(?:[0-9]|1[0-6])：'
```

Expected: 两份文档的 17 个阶段名称和顺序一致。

- [ ] **Step 5: 检查占位词和格式**

Run:

```powershell
Select-String -Path 'docs\FULLSTACK_TECH_DESIGN.md',
  'docs\P1_AGENT_RUN_CONTRACT.md',
  'docs\DATABASE_SCHEMA_REVISION_STRATEGY.md' `
  -Pattern 'TODO','TBD','待定'

git diff --check
```

Expected: 无未解释占位词；`git diff --check` 无错误。

- [ ] **Step 6: 检查文档变更范围**

Run:

```powershell
git diff --name-only HEAD~3..HEAD
```

Expected: 只包含三份目标文档；工作区原有代码改动没有进入文档提交。

- [ ] **Step 7: 输出最终需求菜单摘要**

最终报告包含：

```text
修改文件
主要契约变化
P0-P16 当前状态
下一项推荐需求
验证结果
未修改内容
```
