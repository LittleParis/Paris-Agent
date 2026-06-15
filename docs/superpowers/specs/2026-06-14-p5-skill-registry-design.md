# P5 Skill Registry 技术设计规格

## 1. 任务目标

P5 为 Paris Agent 建立版本化 Skill Registry，使 Skill 从普通字符串升级为经过校验、发布、查询和 Run 绑定的能力包。

```text
Skill YAML
→ Loader
→ Validator
→ 启动事务同步
→ agent_skills / agent_skill_versions
→ Registry 查询与 Skill 选择
→ 创建 Agent Run
→ agent_skill_runs 不可变快照
→ skill.matched 事件
→ 现有 Mock Runner
```

本阶段实现 Skill 注册、查询、显式选择、默认选择和版本审计，不执行真实 Skill Prompt、工具、RAG、Memory 或 DAG Workflow。

## 2. 相关文档

- `AGENTS.md`
- `docs/FULLSTACK_TECH_DESIGN.md`
- `docs/superpowers/specs/2026-06-14-p4-sse-event-stream-design.md`

## 3. 前置条件

- P4 已完成 `runtime_events` 持久化和 SSE 稳定事件信封。
- `POST /api/agent/runs` 已支持可选 `skill_id` 字段，但当前未验证或绑定版本。
- `backend/app/skills/definitions/` 已存在，当前没有 Skill 定义。
- 前端 ChatPage 已支持创建单个活跃 Run 和消费 Runtime Event。

## 4. 本次范围

### 4.1 后端

- 定义完整的 Skill YAML Pydantic Schema。
- 实现 Skill Definition Loader、Validator、Synchronizer 和 Registry Service。
- 在 FastAPI lifespan 启动阶段严格同步 YAML。
- 新增 `agent_skills`、`agent_skill_versions`、`agent_skill_runs`。
- 新增 SQLAlchemy Model、Repository 和 Alembic Migration。
- 新增 Skill 列表和详情 API。
- 支持显式 Skill 选择和固定默认 `tech_qa`。
- 创建 Run 时绑定不可变 Skill Version 快照。
- 新增 `skill.matched` Runtime Event。
- 提交第一批 8 个最小合法 Skill YAML。

### 4.2 前端

- 新增 Skill API Client。
- 新增 `SkillSelector`。
- 新增 `SlashCommandMenu` 初版。
- Chat Composer 展示和提交当前 Skill。
- Runtime 面板展示实际 Skill、版本和选择模式。

### 4.3 测试

- Skill YAML Loader 和 Validator 单元测试。
- 启动同步和 Repository 测试。
- Skill API 契约测试。
- Run 与 Skill Version 绑定测试。
- Runtime Event 顺序测试。
- 前端 TypeScript/Vite 构建和手动交互验证。

## 5. 明确不做

- Skill Prompt 或 Workflow 的真实执行。
- Skill Executor 到 DAG Plan 的转换。
- LLM 自动 Skill Router。
- 基于 `task_type`、关键词或分类器的静态路由。
- Tool Manager、工具执行或工具审批。
- Memory、RAG、Sandbox 或 Celery 集成。
- Skill 热加载。
- Skill 管理、编辑、启停或发布 API。
- `/skills` 管理页面。
- 一个 Run 执行多个 Skill。

## 6. 设计方案

采用“分层 Registry + 数据库发布快照”：

```text
SkillDefinitionLoader
→ SkillDefinitionValidator
→ SkillSynchronizer
→ SkillRepository / SkillVersionRepository
→ SkillRegistryService
→ SkillSelectionService
```

职责划分：

- YAML 是 Skill 定义源码和开发时事实来源。
- 数据库是已发布 Skill 的查询投影、状态记录和版本审计来源。
- Loader 只负责发现和解析文件。
- Validator 只负责结构和跨文件规则校验。
- Synchronizer 只负责将完整合法定义集事务性同步到数据库。
- Registry Service 只从数据库读取已发布版本。
- Selection Service 只处理显式选择或默认选择，不做智能路由。

新增 YAML 解析依赖：

```powershell
Set-Location backend
uv add pyyaml
```

不得使用 `pip install` 或手工修改 lock 文件。

## 7. Skill YAML 契约

### 7.1 文件规则

每个 Skill 使用一个文件：

```text
backend/app/skills/definitions/<skill_id>.yaml
```

文件名必须与定义内的 `skill_id` 完全一致。P5 不支持一个文件包含多个版本；发布新版本时更新 YAML 中的版本并重启服务，数据库保留旧版本。

### 7.2 顶层结构

```yaml
skill_id: tech_qa
name: Technical Q&A
description: Answer software engineering questions with structured reasoning.
version: 1.0.0
enabled: true
is_default: true

input_schema: {}
output_schema: {}
prompt: {}
tools: []
workflow: {}
memory_policy: {}
safety_policy: {}
runtime_config: {}
```

必须字段：

```text
skill_id
name
description
version
enabled
is_default
input_schema
output_schema
prompt
tools
workflow
memory_policy
safety_policy
runtime_config
```

### 7.3 标识和版本

- `skill_id` 必须匹配 `^[a-z][a-z0-9_]{1,127}$`。
- `name` 和 `description` trim 后不能为空。
- `version` 使用严格 SemVer：`MAJOR.MINOR.PATCH`。
- P5 不接受预发布或构建元数据，例如 `1.0.0-beta`、`1.0.0+build`。
- 同一加载批次不得出现重复 `skill_id`。
- 数据库中 `(agent_skill_id, version)` 唯一。

### 7.4 JSON Schema

`input_schema` 和 `output_schema` 必须是 JSON 对象，并至少包含：

```yaml
type: object
properties: {}
additionalProperties: false
```

P5 校验 Schema 的基础结构，不引入独立 JSON Schema 校验依赖，也不执行运行时输入输出校验。完整 Schema 执行留到 Skill Executor 阶段。

### 7.5 Prompt

Prompt 使用结构化对象：

```yaml
prompt:
  system: "..."
  instructions:
    - "..."
```

约束：

- `system` 非空。
- `instructions` 是非空字符串数组。
- API 不返回完整 Prompt。
- Prompt 在 `definition_snapshot` 中保留，用于版本审计和后续执行。

### 7.6 Tools

P5 所有 Skill 的 `tools` 必须为空数组：

```yaml
tools: []
```

在 Tool Manager 和 Tool Guardrail 实现前，不允许 Skill 声明或直接调用工具。

### 7.7 Workflow

P5 只允许单节点 Mock Workflow：

```yaml
workflow:
  entrypoint: mock_executor
  nodes:
    - id: mock_executor
      type: mock
      dependencies: []
```

约束：

- `entrypoint` 固定为 `mock_executor`。
- `nodes` 必须恰好包含一个节点。
- 节点 `id` 固定为 `mock_executor`。
- 节点 `type` 固定为 `mock`。
- `dependencies` 必须为空。

该结构是后续 Skill Executor 和 DAG Plan 的输入占位，不代表 P5 已实现 DAG 执行。

### 7.8 Memory Policy

P5 固定不读不写：

```yaml
memory_policy:
  read: false
  write: false
```

### 7.9 Safety Policy

P5 使用声明式占位：

```yaml
safety_policy:
  risk_level: safe
  requires_approval: false
```

约束：

- `risk_level` 固定为 `safe`。
- `requires_approval` 固定为 `false`。
- 该字段只做元数据校验，不代表完整安全层已经实现。

### 7.10 Runtime Config

P5 最小结构：

```yaml
runtime_config:
  timeout_seconds: 60
  max_retries: 0
```

约束：

- `timeout_seconds` 范围 `1..300`。
- `max_retries` 固定为 `0`。
- P5 Mock Runner 不消费这些配置；后续 Harness 阶段使用。

## 8. 第一批 Skill

P5 提交以下 8 个最小合法定义：

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

规则：

- 初始版本统一为 `1.0.0`。
- 全部 `enabled: true`。
- 仅 `tech_qa` 设置 `is_default: true`。
- 全部使用 P5 Mock Workflow。
- 全部 `tools: []`。
- 全部 Memory Policy 为不读不写。
- 名称、描述、Prompt 和 Schema 应准确表达未来能力，但不得宣称对应 RAG、Memory、Sandbox 或 Codex 执行能力当前已经可用。

## 9. Loader 与 Validator

### 9.1 SkillDefinitionLoader

职责：

- 从固定 definitions 目录读取扩展名为 `.yaml` 或 `.yml` 的普通文件。
- 按文件名排序，保证错误输出稳定。
- 使用 `yaml.safe_load`。
- 拒绝空文件、非对象根节点和 YAML 语法错误。
- 返回带 `source_path` 的未发布定义对象。

Loader 不访问数据库，不修改应用状态。

### 9.2 SkillDefinitionValidator

单文件校验：

- Pydantic 字段类型和必填项。
- 文件名与 `skill_id` 一致。
- 标识、SemVer、JSON Schema、Prompt、Tools、Workflow 和策略约束。

定义集校验：

- 必须至少包含 8 个规定 Skill。
- 允许增加其他符合相同契约的 Skill。
- 不允许重复 `skill_id`。
- 必须恰好一个 `is_default: true`。
- 默认 Skill 必须是 `tech_qa`。
- 默认 Skill 必须启用。

任一错误应携带文件名和字段位置，便于启动时定位。

## 10. 数据模型

### 10.1 `agent_skills`

表示逻辑 Skill，不保存完整版本内容。

```text
id                  BIGINT IDENTITY PRIMARY KEY
skill_id            TEXT NOT NULL UNIQUE
name                TEXT NOT NULL
description         TEXT NOT NULL
enabled             BOOLEAN NOT NULL DEFAULT true
default_version_id  BIGINT NULL
created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

约束：

- `skill_id` 格式符合 snake_case 规则。
- `name` 和 `description` 非空白。
- `default_version_id` 在版本插入后设置，外键指向 `agent_skill_versions.id`。
- 为避免循环建表问题，Migration 先创建两张表，再添加默认版本外键。

### 10.2 `agent_skill_versions`

表示不可变发布版本。

```text
id                   BIGINT IDENTITY PRIMARY KEY
version_id           UUID NOT NULL UNIQUE
agent_skill_id       BIGINT NOT NULL
version              TEXT NOT NULL
definition_snapshot  JSONB NOT NULL
content_hash         TEXT NOT NULL
source_path          TEXT NOT NULL
published_at         TIMESTAMPTZ NOT NULL DEFAULT now()
```

约束：

- 外键 `agent_skill_id → agent_skills.id`，`ON DELETE RESTRICT`。
- 唯一约束 `(agent_skill_id, version)`。
- `version` 满足 P5 SemVer 格式。
- `definition_snapshot` 必须为 JSON 对象。
- `content_hash` 使用规范化 JSON 的 SHA-256 十六进制字符串。
- `source_path` 保存相对 definitions 目录的文件名，不保存宿主机绝对路径。
- 已发布版本不提供更新或删除 Repository 方法。

### 10.3 `agent_skill_runs`

表示一次 Run 实际选择的 Skill Version。

```text
id                   BIGINT IDENTITY PRIMARY KEY
skill_run_id         UUID NOT NULL UNIQUE
run_id               UUID NOT NULL UNIQUE
skill_version_id     BIGINT NOT NULL
selection_mode       TEXT NOT NULL
definition_snapshot  JSONB NOT NULL
created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
```

约束：

- 外键 `run_id → agent_runs.run_id`，`ON DELETE CASCADE`。
- 外键 `skill_version_id → agent_skill_versions.id`，`ON DELETE RESTRICT`。
- `selection_mode IN ('explicit', 'default')`。
- `definition_snapshot` 必须为 JSON 对象。
- P5 每个 Run 恰好一条 Skill Run 记录，因此 `run_id` 唯一。

该表独立于 `agent_runs.skill_id`：

- `agent_runs.skill_id` 保存轻量、可读的最终 Skill ID。
- `agent_skill_runs` 保存真实版本外键、选择方式和不可变定义快照。
- 后续支持多 Skill 编排时，可以通过 Migration 放宽 `run_id` 唯一约束并增加执行顺序，无需改变历史版本表。

## 11. 内容 Hash 与不可变规则

定义规范化流程：

1. 将已通过 Pydantic 校验的 Skill Definition 转为 JSON 兼容对象。
2. 排除 `source_path` 等文件系统元数据。
3. 使用排序 key、固定分隔符和 UTF-8 编码序列化。
4. 计算 SHA-256。

同步语义：

- 数据库不存在该 `skill_id + version`：插入新版本。
- 已存在且 hash 相同：幂等复用。
- 已存在但 hash 不同：视为已发布版本被篡改，阻止服务启动。
- YAML 版本升级：插入新版本，旧版本保留。
- YAML 删除旧版本：数据库不物理删除历史版本。
- 整个 Skill 从 YAML 定义集移除：逻辑 Skill 自动设为 `enabled=false`，历史版本和 Run 绑定保留。

## 12. 启动严格同步

FastAPI lifespan 启动顺序：

```text
加载全部 YAML
→ 校验全部单文件
→ 校验完整定义集
→ 开启数据库事务
→ upsert agent_skills
→ 插入或验证 agent_skill_versions
→ 设置 default_version_id
→ 提交事务
→ 标记 Registry Ready
→ 接受请求
```

严格失败条件：

- YAML 语法错误或字段缺失。
- 空文件或根节点不是对象。
- 文件名与 `skill_id` 不一致。
- 非法 SemVer。
- 重复 Skill。
- 缺少规定的 8 个 Skill。
- 不是恰好一个默认 Skill。
- 默认项不是 `tech_qa` 或默认项被禁用。
- JSON Schema 结构非法。
- Tools 非空。
- Workflow 不是 P5 单节点 Mock 结构。
- 同版本 hash 与数据库不一致。
- 数据库同步失败。

必须先完成整个定义集校验，才开始数据库写入。数据库同步使用单事务，任何失败都不得留下部分发布结果。

P5 不热加载。YAML 变化后必须重启服务。

## 13. Repository 与服务

### 13.1 Repository

建议边界：

```text
SkillRepository
  get_by_skill_id
  list
  upsert_metadata
  set_default_version

SkillVersionRepository
  get_by_skill_and_version
  get_by_id
  create_immutable

AgentSkillRunRepository
  create_binding
  get_by_run_id
```

同步器可使用专用 Repository 方法，但普通 Registry 查询不得修改版本记录。

### 13.2 SkillRegistryService

职责：

- 列出 Skill。
- 获取单个 Skill 及其默认版本。
- 解析启用的默认版本。
- 检查 Registry Ready 状态。
- 将数据库 Model 映射为公开 Schema。

Registry Service 以数据库为运行时读取来源，不在请求期间重新读取 YAML。

### 13.3 SkillSelectionService

输入：

```text
requested_skill_id: string | null
```

输出：

```text
skill
skill_version
selection_mode
definition_snapshot
```

规则：

- 显式传入 `skill_id`：选择对应启用 Skill，`selection_mode=explicit`。
- 未传 `skill_id`：固定选择 `tech_qa`，`selection_mode=default`。
- 未知或禁用 Skill：拒绝创建 Run。
- 默认 Skill 不存在、未启用或没有默认版本：Registry 不可用。

P5 不读取用户输入内容，不根据 `task_type` 做映射，也不调用 LLM。

## 14. Run 创建事务

当前 `AgentRunRepository.create` 会自行提交，不适合同时写入 `agent_skill_runs`。P5 将事务边界提升到应用服务：

```text
解析 Skill Selection
→ 构造 AgentRun
→ flush 获取 Run 数据
→ 构造 AgentSkillRun
→ commit 单一事务
→ 启动 Mock Runner
```

要求：

- `agent_runs.skill_id` 写入最终解析后的 ID。
- `agent_skill_runs.skill_version_id` 指向实际默认版本。
- `agent_skill_runs.definition_snapshot` 复制已发布版本快照。
- 任一写入失败时整体回滚。
- 提交成功前不得启动 Mock Runner。
- P5 不修改现有 Run 状态机。

## 15. Runtime Event

新增事件类型：

```text
skill.matched
```

事件 payload：

```json
{
  "skill_id": "tech_qa",
  "skill_version": "1.0.0",
  "selection_mode": "default"
}
```

事件顺序：

```text
skill.matched
run.started
node.started
message.delta
message.delta
node.completed
run.completed
```

规则：

- `skill.matched` 是成功创建并启动的 Run 的第一条 Runtime Event。
- 事件由 Mock Runner 启动后从 `agent_skill_runs` 读取真实绑定信息并发布。
- 不允许直接信任客户端请求中的 Skill ID 构造事件。
- 事件状态使用 `queued`，因为发布时 Run 尚未进入 `running`。

## 16. API 设计

### 16.1 Skill 列表

```http
GET /api/skills?include_disabled=false
```

查询参数：

- `include_disabled=false`：默认，仅返回启用 Skill。
- `include_disabled=true`：返回启用和禁用 Skill。

列表项：

```json
{
  "skill_id": "tech_qa",
  "name": "Technical Q&A",
  "description": "...",
  "enabled": true,
  "version": "1.0.0",
  "is_default": true
}
```

排序：

- 默认 Skill 第一。
- 其余按 `name`、`skill_id` 稳定排序。

### 16.2 Skill 详情

```http
GET /api/skills/{skill_id}
```

返回默认版本的公开定义：

```text
skill_id
name
description
enabled
version
is_default
input_schema
output_schema
tools
workflow summary
memory_policy
safety_policy
runtime_config
```

不返回：

- 内部数据库 ID。
- `content_hash`。
- `source_path`。
- 完整 Prompt。
- 历史版本列表。

未知 Skill 返回 `404`。详情接口可读取禁用 Skill，便于诊断；是否允许 Run 使用由 Selection Service 决定。

### 16.3 Run 创建

请求继续使用：

```json
{
  "input": "...",
  "skill_id": "tech_qa"
}
```

`skill_id` 可选。

错误：

- 显式 Skill 未知：`422`。
- 显式 Skill 禁用：`422`。
- Registry 尚未 Ready：`503`。
- 默认 Skill 配置异常：`503`。

Run 创建和读取响应增加：

```text
skill_id
skill_version
skill_selection_mode
```

`AgentRunCreated` 返回最终解析后的 Skill 信息，避免前端只能等待事件才知道实际选择。

`skill_version` 和 `skill_selection_mode` 通过 `agent_skill_runs → agent_skill_versions` 关联查询生成，不在 `agent_runs` 中重复增加版本和选择方式列。P5 新建 Run 的创建响应中三项均非空；读取已有 P2-P4 历史 Run 时，版本和选择方式可为 `null`。

## 17. 前端设计

### 17.1 Skill API Client

新增：

```text
listSkills()
getSkill(skillId)
```

页面和组件不得直接拼接请求 URL。

### 17.2 SkillSelector

职责：

- 加载启用 Skill 列表。
- 默认显示“Default · tech_qa”，内部选择值保持 `null`。
- 显示名称、ID 和版本。
- 选择变化时向 ChatPage/Store 提供 `skill_id`。
- 加载失败时显示错误并禁止提交，避免创建与界面选择不一致的 Run。

选择语义：

- `selectedSkillId=null`：由后端执行默认选择，记录 `selection_mode=default`。
- 用户主动选择任意 Skill，包括 `tech_qa`：发送对应 `skill_id`，记录 `selection_mode=explicit`。
- Selector 提供“Use default”选项，可将选择恢复为 `null`。

P5 使用现有 Axios Client。Skill 列表是服务端查询缓存，可使用 TanStack Query；不得同时在 Pinia 中维护同一份列表缓存。

### 17.3 SlashCommandMenu

触发规则：

- Composer 文本 trim 前缀为 `/` 时显示。
- 菜单项来自 Skill 列表。
- 命令格式为 `/<skill_id>`。
- 选择菜单项只更新 SkillSelector，并移除输入框中的命令前缀。
- 不发送消息，不执行 Workflow，不解析命令参数。
- Escape 关闭菜单，方向键和 Enter 支持基础键盘选择。

### 17.4 MessageInput

MessageInput 继续管理本地文本，但增加：

- 接收 Skill 列表或 Slash Menu 配置。
- 发出 Skill 选择事件。
- 在输入区上方或 footer 显示当前 Skill。
- 提交事件仍只发送消息文本，由 ChatPage/Store 同时读取当前 Skill。

### 17.5 Agent Run Store

新增当前选择：

```text
selectedSkillId: string | null
```

提交时：

```text
createAgentRun({
  input,
  task_type: "chat",
  skill_id: selectedSkillId ?? undefined
})
```

Runtime Event 处理新增 `skill.matched`，更新并展示：

```text
skill_id
skill_version
selection_mode
```

后端创建响应仍是最终事实，前端选中值不能覆盖响应或事件中的实际绑定。

### 17.6 Runtime 面板

新增字段：

- Skill ID。
- Skill Version。
- Selection Mode。

事件时间线正常展示 `skill.matched`。P5 不实现完整 SkillRunPanel、Workflow Viewer 或 Prompt 查看器。

## 18. 错误处理

### 18.1 启动错误

Skill 定义或同步错误应阻止应用启动，并输出：

- 文件名。
- Skill ID（可解析时）。
- 字段位置。
- 错误原因。

不得跳过非法文件后继续启动。

### 18.2 Registry 未初始化

若应用生命周期异常导致 Registry 未 Ready：

- Skill API 返回 `503`。
- Run 创建返回 `503`。
- 不退化为无 Skill Run。

### 18.3 Run 绑定失败

- 数据库事务回滚。
- 不启动 Mock Runner。
- 不创建 Runtime Event。
- API 返回可读错误，不泄露数据库内部信息。

### 18.4 前端 Skill 加载失败

- 展示错误状态。
- 禁止消息提交。
- 提供重新加载动作。
- 不静默回退到硬编码 Skill，以免 UI 与后端 Registry 漂移。

## 19. 需要修改的文件

预计修改：

```text
backend/app/main.py
backend/app/schemas/agent.py
backend/app/agent/mock_runner.py
backend/app/api/__init__.py
backend/app/api/routes_agent.py
backend/app/db/models/__init__.py
backend/app/db/repositories/agent_runs.py
backend/app/db/repositories/__init__.py
backend/app/db/session.py
backend/alembic/env.py
backend/pyproject.toml
backend/uv.lock
backend/tests/conftest.py
backend/tests/test_agent_runs_api.py
frontend/src/api/agent.ts
frontend/src/api/agentEvents.ts
frontend/src/stores/agentRun.ts
frontend/src/pages/ChatPage.vue
frontend/src/components/chat/AgentRunPanel.vue
frontend/src/components/chat/MessageInput.vue
frontend/src/styles/main.css
docs/FULLSTACK_TECH_DESIGN.md
```

预计新增：

```text
backend/app/api/routes_skills.py
backend/app/schemas/skill.py
backend/app/skills/loader.py
backend/app/skills/validator.py
backend/app/skills/synchronizer.py
backend/app/skills/registry.py
backend/app/skills/selection.py
backend/app/db/models/agent_skill.py
backend/app/db/models/agent_skill_version.py
backend/app/db/models/agent_skill_run.py
backend/app/db/repositories/skills.py
backend/alembic/versions/20260614_0003_create_skill_registry.py
backend/app/skills/definitions/tech_qa.yaml
backend/app/skills/definitions/learning_path.yaml
backend/app/skills/definitions/document_ingest.yaml
backend/app/skills/definitions/rag_eval.yaml
backend/app/skills/definitions/memory_consolidation.yaml
backend/app/skills/definitions/code_sandbox.yaml
backend/app/skills/definitions/project_summary.yaml
backend/app/skills/definitions/codex_task.yaml
backend/tests/test_skill_definitions.py
backend/tests/test_skill_registry.py
backend/tests/test_skills_api.py
frontend/src/api/skills.ts
frontend/src/components/chat/SkillSelector.vue
frontend/src/components/chat/SlashCommandMenu.vue
```

实施计划可以为保持单一职责拆分少量辅助文件，但不得改变顶层目录结构或引入无关模块。

## 20. 测试与验证

### 20.1 Loader 和 Validator

覆盖：

- 8 个合法 YAML 全部加载。
- YAML 语法错误。
- 空文件和非对象根节点。
- 缺少字段。
- 文件名与 Skill ID 不一致。
- 非法 ID 和非法 SemVer。
- 重复 Skill。
- 缺少或存在多个默认 Skill。
- 默认项不是 `tech_qa` 或被禁用。
- 非对象 JSON Schema。
- 非空 Tools。
- 非 Mock Workflow。
- 非法 Memory/Safety/Runtime Policy。

### 20.2 Synchronizer 和 Repository

覆盖：

- 首次发布写入 8 个 Skill 和 8 个版本。
- 第二次同步幂等。
- 新版本发布后旧版本保留。
- 增加第 9 个合法 Skill 时可正常发布。
- 同版本同 hash 复用。
- 同版本不同 hash 阻止同步。
- 同步中途失败整体回滚。
- `default_version_id` 指向当前 YAML 版本。
- 从 YAML 移除整个 Skill 后将逻辑项禁用，并保留历史版本。

### 20.3 API

覆盖：

- 默认列表只返回启用 Skill。
- `include_disabled=true` 返回全部。
- 列表排序和默认标识。
- 详情返回公开字段，不返回 Prompt、hash 或 source path。
- 未知 Skill 返回 `404`。
- Registry 未 Ready 返回 `503`。

### 20.4 Run 绑定

覆盖：

- 显式选择 Skill。
- 未选择时默认 `tech_qa`。
- 未知和禁用 Skill 返回 `422`。
- Run 与 AgentSkillRun 在同一事务创建。
- `agent_runs.skill_id` 与版本快照一致。
- 每个 Run 恰好一个 AgentSkillRun。
- 绑定失败不启动 Runner。
- `skill.matched` 是 sequence 1。
- `run.started` 是 sequence 2。
- 事件 payload 来自数据库绑定。
- Run 创建和读取响应包含 Skill ID、版本和选择模式。

### 20.5 Migration

PostgreSQL 环境：

```powershell
Set-Location backend
uv run alembic upgrade head
uv run alembic downgrade 20260614_0002
uv run alembic upgrade head
```

检查：

- 三张 Skill 表。
- 默认版本循环外键处理。
- 唯一约束和删除策略。
- JSONB 对象约束。
- downgrade 顺序正确。

### 20.6 自动验证

```powershell
Set-Location backend
uv run pytest

Set-Location ..\frontend
pnpm build
```

### 20.7 手动联调

1. 启动后端，确认 8 个 YAML 同步成功。
2. 请求 `/api/skills`，确认默认 Skill 第一。
3. 打开 `/chat`，确认 SkillSelector 默认选择 `tech_qa`。
4. 输入 `/`，确认 Slash Command Menu 展示 8 个 Skill。
5. 选择 `learning_path`，确认输入框不直接提交。
6. 发送消息，确认 POST 携带 `learning_path`。
7. 确认创建响应和 Runtime 面板显示 `learning_path@1.0.0`、`explicit`。
8. 选择“Use default”，确认请求省略 `skill_id`，并记录 `tech_qa@1.0.0`、`default`。
9. 确认事件时间线第一条为 `skill.matched`。
10. 将测试 Skill 设为禁用，确认列表隐藏且 Run 创建被拒绝。
11. 修改已发布同版本内容，确认后端启动失败并报告版本冲突。

## 21. 风险点

- 启动严格同步意味着数据库不可用或 Skill 定义非法时 API 不启动，这是有意的 fail-fast 行为。
- YAML 是单文件当前版本，数据库保留历史版本；要查看或回滚旧版本，需要后续发布工具，P5 不提供。
- P5 不执行 JSON Schema、Prompt、Workflow 和 Runtime Config，它们只是经过校验的版本化契约。
- `agent_skill_runs.run_id` 唯一只适用于 P5 单 Skill Run；多 Skill 编排阶段需要显式 Migration。
- 前端 Slash Command 只选择 Skill，不应演变为绕过 API 或 Tool Manager 的命令执行入口。
- 完整 Prompt 不通过公开 API 返回，但仍存储在数据库快照中；后续权限与审计阶段需要限制数据库和管理接口访问。
- P5 引入 `PyYAML`，会合理修改 `pyproject.toml` 和 `uv.lock`，需要在变更总结中说明。

## 22. 完成标准

- 8 个 Skill YAML 通过完整校验。
- 应用启动时全量校验并单事务同步。
- `agent_skills`、`agent_skill_versions`、`agent_skill_runs` 通过 Migration 创建。
- 已发布版本不可原地修改，同版本篡改阻止启动。
- Skill 列表和详情 API 可用。
- 显式选择与默认 `tech_qa` 均可创建 Run。
- 每个 Run 记录真实 Skill Version 和不可变快照。
- `skill.matched` 是 Run 的第一条 Runtime Event。
- 前端可通过 SkillSelector 和 Slash Command Menu 选择 Skill。
- Runtime 面板展示实际 Skill、版本和选择模式。
- 后端测试、Migration 验证和前端构建通过。
- 未实现复杂自动路由、真实 Skill 执行或工具调用。
