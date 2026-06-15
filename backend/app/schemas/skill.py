"""P5 Skill 定义与 API 响应的 Pydantic 契约。"""

import re

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

# ---------- 常量正则 ----------

# skill_id: 小写字母开头，后跟小写字母 / 数字 / 下划线，总长 2-128
_SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,127}$")

# 严格 SemVer MAJOR.MINOR.PATCH — 不允许前导零、预发布标签或构建元数据
_SEMVER_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")


# ===================================================================
# 子模型
# ===================================================================


class SkillPrompt(BaseModel):
    """Skill 提示词配置。"""

    system: str
    instructions: list[str]

    @field_validator("system")
    @classmethod
    def system_must_not_be_blank(cls, value: str) -> str:
        """system 提示词去除空白后不可为空。"""
        if not value.strip():
            raise ValueError("system must not be blank")
        return value

    @field_validator("instructions")
    @classmethod
    def instructions_must_be_non_empty(cls, value: list[str]) -> list[str]:
        """指令列表至少包含一条非空指令。"""
        if not value:
            raise ValueError("instructions must not be empty")
        for i, item in enumerate(value):
            if not item.strip():
                raise ValueError(f"instructions[{i}] must not be blank")
        return value


class SkillWorkflowNode(BaseModel):
    """P5 工作流节点 — 仅允许单个 mock_executor。"""

    id: str
    type: str
    dependencies: list

    @field_validator("id")
    @classmethod
    def id_must_be_mock_executor(cls, value: str) -> str:
        if value != "mock_executor":
            raise ValueError('node id must be "mock_executor"')
        return value

    @field_validator("type")
    @classmethod
    def type_must_be_mock(cls, value: str) -> str:
        if value != "mock":
            raise ValueError('node type must be "mock"')
        return value

    @field_validator("dependencies")
    @classmethod
    def dependencies_must_be_empty(cls, value: list) -> list:
        if value:
            raise ValueError("dependencies must be empty for P5")
        return value


class SkillWorkflow(BaseModel):
    """P5 工作流 — entrypoint 固定为 mock_executor，仅含一个节点。"""

    entrypoint: str
    nodes: list[SkillWorkflowNode]

    @field_validator("entrypoint")
    @classmethod
    def entrypoint_must_be_mock_executor(cls, value: str) -> str:
        if value != "mock_executor":
            raise ValueError('entrypoint must be "mock_executor"')
        return value

    @field_validator("nodes")
    @classmethod
    def nodes_must_have_exactly_one(cls, value: list[SkillWorkflowNode]) -> list[SkillWorkflowNode]:
        if len(value) != 1:
            raise ValueError("workflow must have exactly 1 node for P5")
        return value


class SkillMemoryPolicy(BaseModel):
    """P6 memory permissions carried by an immutable Skill version."""

    read: bool
    write: bool

    @model_validator(mode="after")
    def write_requires_read(self) -> "SkillMemoryPolicy":
        if self.write and not self.read:
            raise ValueError("memory write requires read")
        return self


class SkillSafetyPolicy(BaseModel):
    """P5 安全策略 — 固定为 safe / 无需审批。"""

    risk_level: str
    requires_approval: bool

    @field_validator("risk_level")
    @classmethod
    def risk_level_must_be_safe(cls, value: str) -> str:
        if value != "safe":
            raise ValueError('risk_level must be "safe"')
        return value

    @field_validator("requires_approval")
    @classmethod
    def requires_approval_must_be_false(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError("requires_approval must be False for P5")
        return value


class SkillRuntimeConfig(BaseModel):
    """Skill 运行时配置。"""

    timeout_seconds: int = Field(ge=1, le=300)
    max_retries: int

    @field_validator("max_retries")
    @classmethod
    def max_retries_must_be_zero(cls, value: int) -> int:
        if value != 0:
            raise ValueError("max_retries must be 0 for P5")
        return value


# ===================================================================
# 主定义模型（对应 YAML 文件结构）
# ===================================================================


class SkillDefinition(BaseModel):
    """Skill YAML 文件的完整 Pydantic 映射，含全部 P5 阶段约束。"""

    skill_id: str
    name: str
    description: str
    version: str
    enabled: bool
    is_default: bool
    input_schema: dict
    output_schema: dict
    prompt: SkillPrompt
    tools: list
    workflow: SkillWorkflow
    memory_policy: SkillMemoryPolicy
    safety_policy: SkillSafetyPolicy
    runtime_config: SkillRuntimeConfig

    # --- 基础字段校验 ---

    @field_validator("skill_id")
    @classmethod
    def validate_skill_id(cls, value: str) -> str:
        """skill_id 必须匹配 ^[a-z][a-z0-9_]{1,127}$。"""
        if not _SKILL_ID_RE.match(value):
            raise ValueError(
                "skill_id must match ^[a-z][a-z0-9_]{1,127}$"
            )
        return value

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        """name 去除首尾空白后不可为空。"""
        if not value.strip():
            raise ValueError("name must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        """description 去除首尾空白后不可为空。"""
        if not value.strip():
            raise ValueError("description must not be blank")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """严格 SemVer MAJOR.MINOR.PATCH，禁止预发布标签与构建元数据。"""
        if not _SEMVER_RE.match(value):
            raise ValueError(
                "version must be strict SemVer MAJOR.MINOR.PATCH "
                "(no pre-release or build metadata)"
            )
        return value

    # --- JSON Schema 结构校验 ---

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict) -> dict:
        """input_schema 必须为 type=object + properties={} + additionalProperties=false。"""
        return _validate_json_schema_structure(value, "input_schema")

    @field_validator("output_schema")
    @classmethod
    def validate_output_schema(cls, value: dict) -> dict:
        """output_schema 必须为 type=object + properties={} + additionalProperties=false。"""
        return _validate_json_schema_structure(value, "output_schema")

    # --- P5 阶段约束 ---

    @field_validator("tools")
    @classmethod
    def tools_must_be_empty(cls, value: list) -> list:
        """P5 阶段 tools 列表必须为空。"""
        if value:
            raise ValueError("tools must be empty for P5")
        return value

    # --- 跨字段一致性校验 ---

    @model_validator(mode="after")
    def _cross_field_consistency(self) -> "SkillDefinition":
        """确保 workflow.entrypoint 与唯一节点的 id 一致。"""
        wf = self.workflow
        if wf.nodes and wf.entrypoint != wf.nodes[0].id:
            raise ValueError(
                "workflow.entrypoint must match the single node's id"
            )
        if self.memory_policy.write and self.skill_id != "memory_consolidation":
            raise ValueError(
                "only memory_consolidation may enable memory write"
            )
        return self


def _validate_json_schema_structure(value: dict, field_name: str) -> dict:
    """校验 JSON Schema 字典必须具备 type=object / properties / additionalProperties=false。"""
    if value.get("type") != "object":
        raise ValueError(f"{field_name} must have type: 'object'")
    if "properties" not in value or not isinstance(value["properties"], dict):
        raise ValueError(f"{field_name} must have a 'properties' dict")
    if value.get("additionalProperties") is not False:
        raise ValueError(f"{field_name} must have additionalProperties: false")
    return value


# ===================================================================
# API 响应模型
# ===================================================================


class SkillListItem(BaseModel):
    """技能列表项 — GET /skills 的轻量摘要。"""

    skill_id: str
    name: str
    description: str
    enabled: bool
    version: str
    is_default: bool


class SkillDetail(BaseModel):
    """技能详情 — GET /skills/{skill_id} 的完整响应。

    包含 JSON Schema、workflow 与各项策略；
    不暴露 prompt / content_hash / source_path / 内部 ID。
    """

    skill_id: str
    name: str
    description: str
    enabled: bool
    version: str
    is_default: bool
    input_schema: dict
    output_schema: dict
    tools: list
    workflow: SkillWorkflow
    memory_policy: SkillMemoryPolicy
    safety_policy: SkillSafetyPolicy
    runtime_config: SkillRuntimeConfig


class SkillRunInfo(BaseModel):
    """Agent Run 中携带的技能上下文信息。

    用于 AgentRunCreated / AgentRunRead 的嵌入字段，
    记录本次 Run 关联的技能标识与选择方式。
    """

    skill_id: str | None = None
    skill_version: str | None = None
    skill_selection_mode: str | None = None
