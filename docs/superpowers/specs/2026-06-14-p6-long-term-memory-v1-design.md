# P6 长期记忆 V1 技术设计规格

## 1. 任务目标

P6 为 Paris Agent 建立自研长期记忆 V1，使系统可以管理结构化用户与项目记忆，并让受 Memory Policy 控制的 Skill 在 Mock Run 中检索或显式写入记忆。

```text
手动 Memory CRUD
→ MemoryManager
→ 校验、评分、精确去重
→ agent_memories

可读 Skill Run
→ MemoryRetriever
→ memory.retrieved 事件
→ Mock Runner

memory_consolidation Run
→ MockMemoryExtractor
→ MemoryManager
→ agent_memories
```

P6 使用 PostgreSQL 作为唯一事实存储，不把聊天记录直接等同于长期记忆，也不接入 Milvus、Embedding、复杂语义去重或自动合并。

## 2. 相关文档

- `AGENTS.md`
- `docs/FULLSTACK_TECH_DESIGN.md`
- `docs/DATABASE_SCHEMA_REVISION_STRATEGY.md`
- `docs/superpowers/specs/2026-06-14-p5-skill-registry-design.md`

## 3. 前置条件

- P5 已建立版本化 Skill Registry、Skill Selection 和不可变 Skill Run 快照。
- Agent Run 使用服务端配置中的 `DEFAULT_USER_ID` 作为过渡用户归属。
- P6 暂不引入 `users`、`projects` 或认证系统。
- Skill Definition 的 `memory_policy` 在 P5 固定为不读不写，P6 需要将其升级为可声明策略。
- 当前 Mock Runner 已能发布持久化 Runtime Event。

## 4. 本次范围

### 4.1 后端

- 新增 `agent_memories` SQLAlchemy Model 和 Alembic Migration。
- 新增 Memory Pydantic Schema。
- 实现 Memory Repository、Manager、Retriever、Deduplicator 和 Mock Extractor。
- 实现 Memory 创建、列表、详情、更新、软删除和搜索 API。
- 实现用户归属、用户/项目作用域、来源、标签、评分、版本、过期和软删除规则。
- 使用规范化内容 Hash 完成活跃记忆精确去重。
- 在 Skill Memory Policy 允许时接入 Mock Run 读取。
- 仅 `memory_consolidation` Skill 可通过确定性 Mock Extractor 写入。
- 发布需要 Memory 能力的 Skill `1.1.0`，保留数据库中的 `1.0.0` 历史版本。
- 新增 Memory Runtime Event。

### 4.2 前端

- 新增 `/memory` 页面。
- 新增 Memory API Client。
- 新增 `MemoryPage`、`MemoryList`、`MemoryEditor`。
- 支持过滤、创建、编辑、软删除、过期状态和版本冲突提示。
- Chat Runtime 面板显示本次检索到的记忆摘要。

### 4.3 测试

- Model、Migration、Repository 和 Manager 测试。
- 用户隔离、作用域、去重、软删除、过期和乐观锁测试。
- API 契约、分页、过滤和搜索排序测试。
- Skill 版本升级与旧版本保留测试。
- Mock Run 读取、显式写入、事件顺序和幂等测试。
- 前端 TypeScript/Vite 构建和手动联调验证。

## 5. 明确不做

- 真实认证、`users` 表或 JWT。
- `projects` 表和项目成员授权。
- Milvus Collection、Embedding 生成或向量检索。
- Elasticsearch、Neo4j 或 Graph Memory。
- LLM Memory Extractor、Classifier 或 Scorer。
- 模糊或语义去重。
- 所有普通聊天的自动记忆写入。
- 复杂自动合并、冲突消解或 Memory Consolidation 调度。
- 恢复已软删除记忆的 API。
- 会话历史持久化。
- RabbitMQ、Celery 或异步向量同步。
- 新增前端依赖。

## 6. 设计方案

采用“统一单表 + 分层 Memory Service”：

```text
Memory API / Mock Runner
→ MemoryManager
  ├── MemoryRepository
  ├── MemoryDeduplicator
  └── MemoryRetriever
```

职责：

- `MemoryRepository` 只负责带用户归属条件的数据访问。
- `MemoryManager` 是创建、更新、删除和自动写入的唯一入口。
- `MemoryDeduplicator` 负责规范化内容与精确 Hash。
- `MemoryRetriever` 负责过滤、关键词匹配、评分、排序和访问统计。
- `MockMemoryExtractor` 只解析 `memory_consolidation` 的确定性输入格式。
- PostgreSQL 保存业务事实和未来向量投影同步状态。

不按八种记忆类型拆表。不同类型当前共享相同生命周期、权限和检索字段；过早拆表会重复 API、Repository、Migration 和测试。

## 7. 用户归属与权限

P6 沿用过渡单用户契约：

```text
user_id = Settings.DEFAULT_USER_ID
```

规则：

- 客户端不得提交或覆盖 `user_id`。
- API、Manager 和 Run 从服务端配置注入当前用户 ID。
- Repository 的详情、更新、删除和搜索必须同时带 `memory_id + user_id`。
- 不属于当前用户的记忆与不存在的记忆统一返回 `404`。
- `agent_memories.user_id` P6 不建立 `users` 外键。
- 接入真实认证时，调用方改为认证上下文，不改变 Memory Service 接口的显式 `user_id` 参数。

`project_id` 在 P6 只是作用域标识，不建立 `projects` 外键。项目成员授权留到 Project/Identity 专项阶段。

## 8. 记忆类型与作用域

### 8.1 Memory Type

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

初步语义：

- `short_term`：需要跨少量 Run 保留、允许较短过期时间的临时上下文。
- `learning_profile`：学习目标、熟练度、偏好和节奏。
- `semantic`：稳定事实、概念理解和技术偏好。
- `episodic`：发生过的具体学习或项目事件。
- `project`：项目约束、决策和上下文。
- `procedural`：可复用流程、操作习惯和解决步骤。
- `task`：跨 Run 的任务目标和进度信息。
- `runtime`：诊断或恢复用途的运行信息；P6 只支持手动或 consolidation 写入，不替代 Runtime Event。

### 8.2 Scope

```text
user
project
```

约束：

- `scope=user` 时 `project_id IS NULL`。
- `scope=project` 时 `project_id IS NOT NULL`。
- `memory_type=project` 必须使用 `scope=project`。
- 其他 Memory Type 可以使用用户或项目作用域。

## 9. 数据模型

新增 `agent_memories`：

```text
id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
memory_id           UUID NOT NULL UNIQUE
user_id             UUID NOT NULL
project_id          UUID NULL
memory_type         TEXT NOT NULL
scope               TEXT NOT NULL
content             TEXT NOT NULL
summary             TEXT NULL
importance          NUMERIC(5,4) NOT NULL
confidence          NUMERIC(5,4) NOT NULL
source_type         TEXT NOT NULL
source_id           UUID NULL
source_detail       JSONB NOT NULL DEFAULT '{}'
tags                JSONB NOT NULL DEFAULT '[]'
content_hash        TEXT NOT NULL
version             INTEGER NOT NULL DEFAULT 1
access_count        BIGINT NOT NULL DEFAULT 0
last_accessed_at    TIMESTAMPTZ NULL
expires_at          TIMESTAMPTZ NULL
deleted_at          TIMESTAMPTZ NULL
external_vector_id  TEXT NULL
embedding_version   TEXT NULL
sync_status         TEXT NOT NULL DEFAULT 'not_indexed'
last_synced_at      TIMESTAMPTZ NULL
sync_error          TEXT NULL
created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

### 9.1 字段约束

- `memory_type` 必须属于既定八种类型。
- `scope IN ('user', 'project')`。
- `content` trim 后不能为空。
- `summary` 非空时 trim 后不能为空。
- `importance BETWEEN 0 AND 1`。
- `confidence BETWEEN 0 AND 1`。
- `version >= 1`。
- `access_count >= 0`。
- `source_type IN ('manual', 'agent_run', 'consolidation')`。
- `source_type=manual` 时 `source_id IS NULL`。
- `source_type IN ('agent_run', 'consolidation')` 时 `source_id IS NOT NULL`。
- `source_detail` 必须为 JSON 对象。
- `tags` 必须为 JSON 数组。
- 标签 trim 后非空、去重、稳定排序，每条最多 20 个标签，每个标签最长 64 字符。
- `content_hash` 为 64 位 SHA-256 十六进制字符串。
- `expires_at` 可以是过去或未来的合法时间戳，便于导入历史数据；是否过期由查询时钟判断。
- `deleted_at` 非空表示用户已撤回该记忆。

### 9.2 外部向量投影字段

状态集合：

```text
not_indexed
pending
syncing
succeeded
failed
deleting
deleted
```

P6 只写入：

```text
external_vector_id = null
embedding_version = null
sync_status = not_indexed
last_synced_at = null
sync_error = null
```

这些字段定义未来 Milvus 投影契约，不代表 P6 已构建向量数据库。

## 10. 索引与唯一约束

访问索引：

```text
(user_id, memory_type, updated_at DESC)
(user_id, updated_at DESC)
(project_id, updated_at DESC) WHERE project_id IS NOT NULL
(user_id, expires_at) WHERE expires_at IS NOT NULL AND deleted_at IS NULL
```

精确去重使用 PostgreSQL 部分唯一索引：

```text
UNIQUE (user_id, scope, coalesce(project_id, ZERO_UUID), memory_type, content_hash)
WHERE deleted_at IS NULL
```

语义：

- 同一用户、作用域、项目、类型和规范化内容只能存在一条活跃记录。
- 已软删除记录不阻止重新创建。
- 不同 Memory Type 可保存相同文本。
- 用户作用域和项目作用域互不冲突。
- 不添加 tags GIN 索引；P6 数据量和查询证据不足，标签过滤先使用普通 JSON 条件。

SQLite 测试环境无法完整表达 PostgreSQL 部分表达式唯一索引时，Manager 在应用层执行同样的冲突检查，PostgreSQL Migration 提供最终并发约束。

## 11. 内容规范化与精确去重

规范化流程：

1. Unicode 使用 NFKC 规范化。
2. trim 首尾空白。
3. 连续空白折叠为单个空格。
4. 保留大小写和标点，避免改变代码、路径和技术标识语义。
5. 使用 UTF-8 编码计算 SHA-256。

Hash 输入：

```text
memory_type
scope
project_id 或空值
规范化 content
```

`summary`、评分、标签和来源不参与 Hash。同一事实的评分或标签变化应通过 PATCH 更新现有记录，不创建重复记忆。

冲突行为：

- 手动创建重复活跃内容：返回 `409` 和冲突 `memory_id`。
- consolidation 重复活跃内容：幂等复用现有记录，不增加版本，不覆盖评分。
- 已软删除内容重新创建：创建新的 `memory_id`。
- P6 不尝试判断近义句或部分重叠内容。

## 12. 来源追踪

### 12.1 手动来源

```text
source_type = manual
source_id = null
source_detail = {
  "created_via": "memory_api"
}
```

### 12.2 Agent Run 来源

```text
source_type = agent_run
source_id = <run_id>
source_detail = {
  "skill_id": "...",
  "skill_version": "...",
  "field": "..."
}
```

P6 普通 Run 不自动写入，因此该来源主要为未来兼容和受控应用服务写入预留。

### 12.3 Consolidation 来源

```text
source_type = consolidation
source_id = <run_id>
source_detail = {
  "skill_id": "memory_consolidation",
  "skill_version": "1.1.0",
  "extractor": "deterministic_v1"
}
```

P6 不给 `source_id` 建立 `agent_runs` 外键。记忆的保留周期可能长于 Run，且未来可能发生 Run 归档；来源通过 UUID 保持可追踪性。

## 13. 版本、更新与删除

### 13.1 乐观锁

PATCH 请求必须包含客户端当前看到的 `version`。

更新条件：

```text
memory_id = ?
AND user_id = ?
AND version = ?
AND deleted_at IS NULL
```

成功后：

```text
version = version + 1
updated_at = now()
```

若资源存在但版本不匹配，返回 `409`。若资源不存在、不属于当前用户或已删除，返回 `404`。

### 13.2 可更新字段

P6 允许修改：

```text
memory_type
scope
project_id
content
summary
importance
confidence
tags
expires_at
```

更新 `memory_type`、`scope`、`project_id` 或 `content` 时重新计算 `content_hash` 并执行冲突检查。

来源字段、创建时间、访问统计和向量投影字段不允许通过普通 PATCH 修改。

### 13.3 软删除

DELETE 必须包含当前 `version`，避免删除已经被其他请求修改的记录。

成功后：

```text
deleted_at = now()
version = version + 1
updated_at = now()
```

P6 不物理删除，不提供恢复接口。默认列表、详情、搜索和 Run 检索都排除软删除记录。

### 13.4 过期

- `expires_at <= now()` 表示已过期。
- 过期不是删除，不修改 `deleted_at`。
- 默认列表和搜索排除过期记录。
- 列表可通过 `include_expired=true` 查看。
- Run 检索永远不使用过期记录。
- P6 不运行自动清理任务。

## 14. Repository

`MemoryRepository` 建议接口：

```text
create
get_owned
list_owned
find_active_duplicate
update_owned_with_version
soft_delete_owned_with_version
search_candidates
touch_access_batch
```

规则：

- 所有公开读写方法必须显式接收 `user_id`。
- 不提供只按 `memory_id` 的业务查询方法。
- Repository 不决定 Memory Policy，也不解析 Run。
- Repository 不自动 commit；事务边界由 Manager 或应用服务管理。
- 列表使用游标分页，游标至少包含排序时间和 `memory_id`，保证稳定翻页。

## 15. MemoryManager

职责：

- 校验作用域、标签、评分、来源和过期时间。
- 规范化内容并计算 Hash。
- 处理手动创建的冲突响应。
- 处理 consolidation 的幂等复用。
- 编排更新、版本冲突和软删除。
- 保证向量投影字段在 P6 保持 `not_indexed`。
- 映射领域错误到 API 层可识别异常。

Manager 不负责搜索评分，不直接读取 Skill YAML。

## 16. MemoryRetriever

### 16.1 输入

```text
user_id
query
memory_types
project_id
tags
limit
include_user_scope
```

Run 检索固定：

- `user_id` 来自 Run。
- `query` 使用 Run 输入。
- `project_id` 使用 Run 的项目 ID。
- `limit=5`。
- 同时允许用户作用域和匹配的项目作用域。

### 16.2 候选过滤

必须满足：

- `user_id` 匹配。
- `deleted_at IS NULL`。
- `expires_at IS NULL OR expires_at > now()`。
- 用户作用域，或 `project_id` 精确匹配的项目作用域。
- 可选 Memory Type 和标签过滤。

不得在没有项目 ID 时召回任意项目作用域记忆。

### 16.3 关键词匹配

P6 不使用 PostgreSQL Full Text Search，也不新增全文索引。

规则：

- 对查询执行 NFKC、trim、空白折叠和小写化。
- 使用空白和常见标点分词。
- 关键词匹配 `content`、`summary` 和 `tags`。
- `text_match` 根据匹配词比例计算到 `0..1`。
- 无查询文本时跳过文本匹配。

该算法是确定性 V1，不宣称等价于语义检索。

### 16.4 综合评分

默认权重：

```text
text_match        0.35
importance        0.25
confidence        0.15
recency           0.10
access_weight     0.10
project_relevance 0.05
```

分量：

- `text_match`：匹配词比例。
- `importance`：数据库评分。
- `confidence`：数据库评分。
- `recency`：基于 `updated_at` 的时间衰减。
- `access_weight`：基于 `log1p(access_count)` 的封顶归一化值。
- `project_relevance`：匹配项目作用域为 1，用户作用域为 0.5。

权重通过 `.env` 配置并在 Settings 中校验：

```text
MEMORY_WEIGHT_TEXT_MATCH
MEMORY_WEIGHT_IMPORTANCE
MEMORY_WEIGHT_CONFIDENCE
MEMORY_WEIGHT_RECENCY
MEMORY_WEIGHT_ACCESS
MEMORY_WEIGHT_PROJECT
MEMORY_RECENCY_HALF_LIFE_DAYS
MEMORY_RETRIEVAL_LIMIT
```

权重必须非负且总和大于 0。应用启动时归一化。

无查询文本时移除 `text_match`，其余权重按比例重新归一化，不把空查询当作零分惩罚。

排序：

```text
score DESC
importance DESC
updated_at DESC
memory_id ASC
```

### 16.5 访问统计

只有 Run 检索成功采用的记忆才更新：

```text
access_count = access_count + 1
last_accessed_at = now()
```

列表、详情、编辑器和普通搜索 API 不增加访问次数。批量更新在单一事务内完成。

## 17. MockMemoryExtractor

P6 不使用 LLM 猜测用户意图。`memory_consolidation` 使用确定性单行格式：

```text
memory_type | scope | project_id-or-empty | content | importance | confidence | comma-separated-tags
```

示例：

```text
learning_profile | user | | 用户正在学习 PostgreSQL 索引优化 | 0.8 | 0.9 | postgresql,index
```

规则：

- 必须恰好 7 个字段。
- `project_id` 为空或合法 UUID。
- `scope=user` 时项目字段必须为空。
- `scope=project` 时项目字段必须为合法 UUID。
- 类型、评分、内容和标签使用与 MemoryManager 相同校验。
- Extractor 输出来源固定为 `consolidation`。
- 格式错误导致 Run 失败，不创建部分记忆。
- 重复输入幂等复用现有活跃记忆。
- P6 每个 consolidation Run 最多写入一条记忆。

该格式是测试与工程闭环协议，不是最终用户体验。后续 LLM Extractor 必须输出同一领域写入命令，再经过 Manager 校验。

## 18. Skill Memory Policy 升级

P5 `SkillMemoryPolicy` 从固定 false 校验升级为声明式布尔策略：

```yaml
memory_policy:
  read: true
  write: false
```

约束：

- `write=true` 要求 `read=true`。
- P6 只有 `memory_consolidation` 允许 `write=true`。
- Skill 是否能读写以 `agent_skill_runs.definition_snapshot` 为准，不读取当前 YAML 猜测历史 Run 策略。

版本发布：

```text
tech_qa@1.1.0               read=true  write=false
learning_path@1.1.0         read=true  write=false
project_summary@1.1.0       read=true  write=false
memory_consolidation@1.1.0  read=true  write=true
```

其余 Skill 保持 `1.0.0` 且：

```text
read=false
write=false
```

不得原地修改已发布 `1.0.0` 的定义内容。启动同步插入 `1.1.0`，数据库保留旧版本和历史 Run 快照。

## 19. Mock Run 集成

### 19.1 读取流程

可读 Skill：

```text
skill.matched
→ memory.retrieval.started
→ MemoryRetriever
→ memory.retrieved
→ run.started
→ node.started
→ message.delta
→ node.completed
→ run.completed
```

不可读 Skill 维持现有流程，不发布 Memory Retrieval Event。

`memory.retrieval.started` payload：

```json
{
  "query": "用户输入",
  "limit": 5,
  "project_id": null
}
```

`memory.retrieved` payload：

```json
{
  "count": 2,
  "memories": [
    {
      "memory_id": "UUID",
      "memory_type": "learning_profile",
      "summary": "用户正在学习 PostgreSQL",
      "score": 0.82
    }
  ]
}
```

事件不返回完整 `content`、来源详情或删除信息，减少 Runtime 面板泄露敏感内容。

Mock 回复只增加可验证占位：

```text
检索到 N 条长期记忆。这是 Paris Agent 的模拟回复。
```

未检索到时：

```text
未检索到长期记忆。这是 Paris Agent 的模拟回复。
```

该文案不宣称已经使用 LLM 做个性化生成。

### 19.2 写入流程

仅 `memory_consolidation@1.1.0`：

```text
skill.matched
→ memory.retrieval.started
→ memory.retrieved
→ run.started
→ memory.write.started
→ MockMemoryExtractor
→ MemoryManager
→ memory.written
→ node.started
→ message.delta
→ node.completed
→ run.completed
```

`memory.write.started` 不包含待写完整内容。

`memory.written` payload：

```json
{
  "memory_id": "UUID",
  "memory_type": "learning_profile",
  "scope": "user",
  "created": true,
  "deduplicated": false
}
```

重复 consolidation：

```json
{
  "created": false,
  "deduplicated": true
}
```

普通成功 Run 不自动写入记忆。

### 19.3 失败语义

- Memory Retrieval 失败：P6 将 Run 标记为 `failed`，发布 `run.failed`，不静默跳过。该选择让早期契约问题可见。
- Consolidation 格式或写入失败：Run 失败，不创建部分数据。
- Runtime Event 写入和 Memory 写入仍是独立数据库事务；完整 Harness/Outbox 一致性留到后续阶段。

## 20. Runtime Event 类型

P6 新增：

```text
memory.retrieval.started
memory.retrieved
memory.write.started
memory.written
```

更新后端 `RuntimeEventType`、Payload Schema 和前端事件联合类型。

Memory Event 只提供 UI 所需摘要，不把完整长期记忆复制到不可变 Runtime Event。

## 21. API 设计

路由前缀：

```text
/api/memories
```

### 21.1 创建

```http
POST /api/memories
```

请求：

```json
{
  "memory_type": "learning_profile",
  "scope": "user",
  "project_id": null,
  "content": "用户正在学习 PostgreSQL 索引优化",
  "summary": "正在学习 PostgreSQL 索引",
  "importance": "0.8000",
  "confidence": "0.9000",
  "tags": ["postgresql", "index"],
  "expires_at": null
}
```

服务端强制：

```text
user_id = DEFAULT_USER_ID
source_type = manual
source_id = null
```

成功返回 `201 Created` 和完整公开资源。

重复活跃内容返回 `409`：

```json
{
  "detail": "An active duplicate memory already exists.",
  "memory_id": "UUID"
}
```

### 21.2 列表

```http
GET /api/memories
```

查询参数：

```text
memory_type
scope
project_id
tag
include_expired=false
limit=20
cursor
```

规则：

- 默认排除软删除和过期。
- `limit` 范围 `1..100`。
- 默认按 `updated_at DESC, memory_id ASC`。
- 返回 `items` 和 `next_cursor`。
- P6 不提供 `include_deleted`。

### 21.3 详情

```http
GET /api/memories/{memory_id}
```

只返回当前用户未删除记忆。过期记忆仍可通过详情查看，便于编辑或延长过期时间。

### 21.4 更新

```http
PATCH /api/memories/{memory_id}
```

请求必须包含：

```json
{
  "version": 3
}
```

以及至少一个可更新字段。成功返回更新后的资源。

版本冲突返回 `409`，包含当前版本号，但不返回其他用户资源信息。

### 21.5 删除

```http
DELETE /api/memories/{memory_id}?version=3
```

成功返回 `204 No Content`。重复删除表现为 `404`。

### 21.6 搜索

```http
POST /api/memories/search
```

请求：

```json
{
  "query": "PostgreSQL 索引",
  "memory_types": ["learning_profile", "semantic"],
  "project_id": null,
  "tags": ["postgresql"],
  "limit": 10
}
```

返回：

```json
{
  "items": [
    {
      "memory": {},
      "score": 0.82,
      "score_breakdown": {
        "text_match": 0.75,
        "importance": 0.8,
        "confidence": 0.9,
        "recency": 0.7,
        "access_weight": 0.2,
        "project_relevance": 0.5
      }
    }
  ]
}
```

搜索 API 不增加访问次数；只有 Run Retriever 会更新访问统计。

## 22. 公开 Memory Schema

响应字段：

```text
memory_id
project_id
memory_type
scope
content
summary
importance
confidence
source_type
source_id
source_detail
tags
version
access_count
last_accessed_at
expires_at
sync_status
created_at
updated_at
```

不返回：

- 内部数据库 `id`。
- `user_id`。
- `content_hash`。
- `external_vector_id`。
- `embedding_version`。
- `sync_error`。
- `deleted_at`。

`sync_status` 在 P6 始终为 `not_indexed`，用于明确向量能力尚未启用。

## 23. 错误语义

- 请求字段非法：`422`。
- 资源不存在、不属于当前用户或已删除：`404`。
- 重复活跃内容：`409`。
- 乐观锁版本冲突：`409`。
- Memory Policy 不允许写入：应用内部拒绝，不提供绕过 Policy 的 Run 路径。
- 数据库约束或不可恢复内部错误：`500`，不返回 SQL 或内部路径。

P6 可以沿用当前 FastAPI `detail` 错误格式；统一 RFC 7807 错误信封仍按总设计后续演进。

## 24. 前端设计

### 24.1 路由与导航

新增：

```text
/memory
```

Workbench 侧栏增加 Memory 导航入口。

### 24.2 Memory API Client

新增：

```text
listMemories
getMemory
createMemory
updateMemory
deleteMemory
searchMemories
```

页面组件不得直接拼接请求 URL。

### 24.3 MemoryPage

页面区域：

```text
顶部：标题、统计摘要、创建按钮
过滤区：type、scope、project、tag、过期状态
主体：MemoryList
侧边或对话框：MemoryEditor
```

P6 保持现有 Workbench 视觉系统，不进行全站重设计。

### 24.4 MemoryList

展示：

- Summary 或 Content 摘要。
- Memory Type。
- Scope 和 Project ID。
- Importance / Confidence。
- Tags。
- Version。
- 过期状态。
- Updated 时间。
- `not_indexed` 向量状态提示。

操作：

- 编辑。
- 软删除确认。
- 加载下一页。

### 24.5 MemoryEditor

支持：

- 创建和编辑。
- 类型、作用域、Project ID 联动校验。
- Content、Summary、评分、Tags 和过期时间。
- 编辑请求携带当前 Version。
- `409` 时提示记录已被更新，要求重新加载，不自动覆盖。

### 24.6 Chat Runtime 面板

新增 Memory 区域：

- 检索状态。
- 检索数量。
- Memory Type、Summary 和 Score。
- 写入结果的 Memory ID 与是否去重。

不显示完整 Memory Content、来源详情或内部同步错误。

## 25. Milvus 分阶段边界

### 25.1 P6

- 建立 PostgreSQL Memory 事实模型。
- 建立外部投影 ID、Embedding Version 和同步状态契约。
- 不启动 Milvus。
- 不生成 Embedding。
- 不执行向量检索。

### 25.2 P7

P7 首次正式接入 Milvus，优先完成文档 Chunk 的 Embedding 和向量检索。

在文档向量链路稳定后，将“Memory Embedding 与 Milvus 投影”作为 P7 内独立小步骤：

```text
Memory 写入/更新
→ sync_status=pending
→ 异步或受控 Embedding
→ Upsert Milvus
→ external_vector_id / embedding_version / succeeded
```

删除：

```text
Memory 软删除
→ sync_status=deleting
→ 删除 Milvus 投影
→ sync_status=deleted
```

检索：

```text
Milvus 召回 memory_id
→ PostgreSQL 按 user_id、project_id、expires_at、deleted_at 再过滤
→ 综合 importance、confidence、recency 和项目相关性排序
```

PostgreSQL 始终是事实存储，Milvus 是可重建投影。P7 Memory 向量化不改变 P6 公开 API。

## 26. 需要修改的文件

预计新增：

```text
backend/app/db/models/agent_memory.py
backend/app/db/repositories/memories.py
backend/app/schemas/memory.py
backend/app/memory/manager.py
backend/app/memory/retriever.py
backend/app/memory/deduplicator.py
backend/app/memory/extractor.py
backend/app/api/routes_memories.py
backend/alembic/versions/20260614_0004_create_agent_memories.py
backend/tests/test_memory_model.py
backend/tests/test_memory_manager.py
backend/tests/test_memory_retriever.py
backend/tests/test_memories_api.py
backend/tests/test_memory_run_integration.py
frontend/src/api/memories.ts
frontend/src/pages/MemoryPage.vue
frontend/src/components/memory/MemoryList.vue
frontend/src/components/memory/MemoryEditor.vue
```

预计修改：

```text
backend/app/core/config.py
backend/.env.example
backend/app/db/models/__init__.py
backend/app/db/repositories/__init__.py
backend/app/schemas/agent.py
backend/app/schemas/skill.py
backend/app/skills/validator.py
backend/app/skills/definitions/tech_qa.yaml
backend/app/skills/definitions/learning_path.yaml
backend/app/skills/definitions/project_summary.yaml
backend/app/skills/definitions/memory_consolidation.yaml
backend/app/agent/mock_runner.py
backend/app/main.py
backend/tests/conftest.py
frontend/src/api/agentEvents.ts
frontend/src/stores/agentRun.ts
frontend/src/components/chat/AgentRunPanel.vue
frontend/src/layouts/WorkbenchLayout.vue
frontend/src/router/index.ts
frontend/src/styles/main.css
docs/FULLSTACK_TECH_DESIGN.md
```

实施计划可以按单一职责拆分少量辅助文件，但不得改变顶层目录结构。

## 27. Migration 验证

PostgreSQL 环境：

```powershell
Set-Location backend
uv run alembic upgrade head
uv run alembic downgrade 20260614_0003
uv run alembic upgrade head
```

检查：

- `agent_memories` 类型和默认值。
- Scope/Project、评分、版本、计数、来源和同步状态 CHECK。
- JSONB 对象/数组 CHECK。
- 部分唯一去重索引。
- 用户、类型、项目和过期访问索引。
- downgrade 不修改 P5 Skill 表或历史版本。

## 28. 自动测试

### 28.1 Model 与 Repository

- 合法八种 Memory Type。
- 非法类型、作用域、评分、版本和计数被拒绝。
- 用户/项目 Scope 约束。
- 来源与 `source_id` 约束。
- Tags 和 Source Detail JSON 类型约束。
- 用户隔离。
- 稳定游标分页。
- 过期和软删除过滤。

### 28.2 Manager 与去重

- 内容规范化 Hash 稳定。
- 同一活跃范围精确重复返回冲突。
- 不同类型、项目或作用域不冲突。
- 软删除后允许重新创建。
- PATCH 重新计算 Hash。
- 版本冲突。
- DELETE 版本冲突。
- consolidation 重复输入幂等。

### 28.3 Retriever

- 用户作用域召回。
- 项目作用域只在项目匹配时召回。
- 过期和软删除永不召回。
- 类型和标签过滤。
- 关键词匹配和确定性排序。
- 空查询权重重新归一化。
- Run 使用后批量增加访问计数。
- 搜索 API 不增加访问计数。

### 28.4 API

- 创建、列表、详情、更新和删除。
- 非法作用域返回 `422`。
- 重复返回 `409` 和冲突 ID。
- 隐藏其他用户资源。
- 版本冲突返回 `409`。
- include_expired 行为。
- 分页和过滤。
- 搜索 score breakdown。

### 28.5 Skill 与 Run

- 四个 Skill 发布 `1.1.0`。
- 数据库中 `1.0.0` 保留。
- 未修改同版本内容 Hash。
- Skill Run 快照保存实际 Memory Policy。
- 可读 Skill 发布 Memory Retrieval Event。
- 不可读 Skill 不发布 Memory Event。
- consolidation 写入一条记忆。
- consolidation 重复输入不重复创建。
- 普通 Run 不写入。
- Memory Event 不包含完整 Content。
- 事件顺序符合契约。
- Retrieval 或写入失败使 Run 失败。

### 28.6 自动命令

```powershell
Set-Location backend
uv run pytest

Set-Location ..\frontend
pnpm build
```

## 29. 手动验证

1. 执行 Migration 并启动后端。
2. 打开 `/memory`，创建用户作用域学习画像记忆。
3. 确认列表显示类型、评分、标签、版本和 `not_indexed`。
4. 编辑记忆，确认版本递增。
5. 使用旧版本再次编辑，确认显示 `409` 冲突。
6. 创建重复内容，确认返回冲突 Memory ID。
7. 软删除后确认默认列表和详情不可见。
8. 使用相同内容重新创建，确认生成新 Memory ID。
9. 创建已过期记忆，确认默认列表和搜索不显示，`include_expired=true` 可查看。
10. 使用 `tech_qa` 创建 Run，确认 Memory Retrieval Event 和摘要面板出现。
11. 使用无读取策略的 Skill 创建 Run，确认不出现 Memory Event。
12. 使用合法确定性格式运行 `memory_consolidation`，确认写入记忆。
13. 重复相同 consolidation，确认返回 deduplicated，不增加记录。
14. 使用非法格式运行 consolidation，确认 Run 失败且没有部分写入。
15. 确认普通 Chat Run 完成后没有自动新增记忆。

## 30. 风险点

- P6 的 `DEFAULT_USER_ID` 不是生产认证。设计通过显式 `user_id` 服务接口和 Repository 所有权条件，为后续认证替换保留边界。
- `project_id` 尚无父表和成员授权，因此 P6 只保证用户维度隔离，不能宣称完整项目权限。
- PostgreSQL 关键词匹配是确定性结构化检索，不是语义检索；语义召回在 P7 Memory Milvus 小步骤实现。
- P6 预留向量同步字段会增加表宽度，但能稳定外部投影状态契约，避免后续改变公开资源语义。
- 使用部分表达式唯一索引时，SQLite 测试不能完全替代 PostgreSQL 并发约束验证，Migration 必须在 PostgreSQL 实测。
- Runtime Event 为不可变记录，只保存 Memory 摘要；即便如此，摘要仍可能包含用户信息，后续可观测性阶段需要统一脱敏和保留策略。
- Run 状态、Memory 写入和 Runtime Event 暂未使用 Outbox 或统一事务，进程在提交之间退出可能产生短暂不一致；完整可靠性留到 Harness/Queue 阶段。
- P5 当前实现可能仍在工作区中未提交。P6 实施前应先确认 P5 测试和 Migration 已稳定，避免在未完成基线上叠加实现。

## 31. 完成标准

- `agent_memories` 通过 Model 和 Alembic Migration 创建。
- 所有 Memory API 强制使用服务端用户归属。
- 用户/项目 Scope、来源、评分、版本、过期和软删除契约生效。
- 活跃记忆支持精确去重，软删除后可重新创建。
- PATCH 和 DELETE 使用乐观锁。
- PostgreSQL Retriever 支持过滤、评分和稳定排序。
- 四个 Skill 正确发布 `1.1.0`，旧版保留。
- 可读 Skill 能在 Mock Run 中检索记忆。
- 仅 `memory_consolidation` 能通过确定性格式写入。
- 普通 Run 不自动保存聊天内容。
- `/memory` 页面支持基础管理。
- Milvus 投影字段和 P7 接入边界明确，但 P6 不启动向量数据库。
- Migration、后端测试和前端构建通过。
