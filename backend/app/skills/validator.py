"""Skill Definition Validator — 跨文件定义集校验。"""

from app.skills.loader import LoadedSkillDefinition


REQUIRED_SKILL_IDS: frozenset[str] = frozenset({
    "tech_qa",
    "learning_path",
    "document_ingest",
    "rag_eval",
    "memory_consolidation",
    "code_sandbox",
    "project_summary",
    "codex_task",
})

REQUIRED_DEFAULT_SKILL_ID = "tech_qa"


class SkillValidationError(Exception):
    """Skill 定义集校验错误。"""
    pass


def validate_skill_definition_set(
    definitions: list[LoadedSkillDefinition],
) -> None:
    """Validate the complete set of loaded skill definitions.

    Raises SkillValidationError with descriptive message on any rule violation.
    收集所有违规项后一次性抛出，而非遇到第一个错误就终止。
    """
    errors: list[str] = []

    # 构建 skill_id -> LoadedSkillDefinition 映射，同时检测重复
    seen_ids: dict[str, str] = {}  # skill_id -> source_path
    for loaded in definitions:
        sid = loaded.definition.skill_id
        if sid in seen_ids:
            errors.append(
                f"重复的 skill_id '{sid}'："
                f"已在 '{seen_ids[sid]}' 中出现，"
                f"又在 '{loaded.source_path}' 中出现"
            )
        else:
            seen_ids[sid] = loaded.source_path

    # 检查必需技能是否全部存在
    present_ids = set(seen_ids.keys())
    missing_ids = REQUIRED_SKILL_IDS - present_ids
    if missing_ids:
        missing_list = ", ".join(sorted(missing_ids))
        errors.append(f"缺少必需的 skill_id: {missing_list}")

    # 收集 is_default=True 的技能
    default_skills: list[LoadedSkillDefinition] = [
        loaded for loaded in definitions
        if loaded.definition.is_default
    ]

    # 必须有且仅有一个 is_default=True
    if len(default_skills) == 0:
        errors.append("必须存在恰好一个 is_default: true 的技能")
    elif len(default_skills) > 1:
        default_names = ", ".join(
            loaded.definition.skill_id for loaded in default_skills
        )
        errors.append(
            f"只能有一个 is_default: true 的技能，"
            f"但发现了 {len(default_skills)} 个: {default_names}"
        )

    # 若恰好存在一个 default，检查其 skill_id 和 enabled 状态
    if len(default_skills) == 1:
        default_skill = default_skills[0]
        default_id = default_skill.definition.skill_id

        if default_id != REQUIRED_DEFAULT_SKILL_ID:
            errors.append(
                f"默认技能必须是 '{REQUIRED_DEFAULT_SKILL_ID}'，"
                f"但实际为 '{default_id}'"
            )

        if not default_skill.definition.enabled:
            errors.append(
                f"默认技能 '{default_id}' 必须处于启用状态 (enabled: true)"
            )

    # 汇总所有错误，一次性抛出
    if errors:
        combined = "; ".join(errors)
        raise SkillValidationError(
            f"Skill 定义集校验失败 ({len(errors)} 项错误): {combined}"
        )
