"""Skill Definition Loader — 从 YAML 文件加载 Skill 定义。"""

from pathlib import Path
from typing import Any

import yaml

from app.schemas.skill import SkillDefinition


# Definitions directory (relative to this file)
_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


class SkillLoadError(Exception):
    """Skill YAML 加载错误。"""

    def __init__(self, source_path: str, message: str) -> None:
        self.source_path = source_path
        super().__init__(f"[{source_path}] {message}")


class LoadedSkillDefinition:
    """已加载的 Skill 定义，携带来源文件路径。"""

    def __init__(self, definition: SkillDefinition, source_path: str) -> None:
        self.definition = definition
        self.source_path = source_path


def _collect_yaml_files(definitions_dir: Path) -> list[Path]:
    """收集目录下所有 .yaml / .yml 文件，去重后按文件名排序返回。"""
    seen: dict[str, Path] = {}
    for pattern in ("*.yaml", "*.yml"):
        for path in definitions_dir.glob(pattern):
            if path.name not in seen:
                seen[path.name] = path
    return sorted(seen.values(), key=lambda p: p.name)


def _parse_single_file(file_path: Path) -> LoadedSkillDefinition:
    """解析单个 YAML 文件并返回 LoadedSkillDefinition。

    校验规则：
    - 文件不可为空
    - 根节点必须是 dict
    - Pydantic 模型验证必须通过
    - 文件名 stem 必须与 skill_id 一致
    """
    filename = file_path.name

    # 读取文件内容
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillLoadError(filename, f"无法读取文件: {exc}") from exc

    # 空文件检查
    if not text.strip():
        raise SkillLoadError(filename, "文件为空")

    # YAML 解析
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SkillLoadError(filename, f"YAML 语法错误: {exc}") from exc

    # 根节点必须是 dict
    if not isinstance(raw, dict):
        raise SkillLoadError(
            filename,
            f"根节点必须是映射(dict)，实际为 {type(raw).__name__}",
        )

    # Pydantic 模型验证
    try:
        definition = SkillDefinition(**raw)
    except Exception as exc:
        # 捕获 ValidationError 或其他构造异常，统一包装为 SkillLoadError
        raise SkillLoadError(
            filename, f"定义校验失败: {exc}"
        ) from exc

    # 文件名 stem 必须与 skill_id 一致
    expected_stem = file_path.stem
    if definition.skill_id != expected_stem:
        raise SkillLoadError(
            filename,
            f"文件名 stem '{expected_stem}' 与 skill_id '{definition.skill_id}' 不匹配",
        )

    return LoadedSkillDefinition(definition=definition, source_path=filename)


def load_all_skill_definitions(
    definitions_dir: Path | None = None,
) -> list[LoadedSkillDefinition]:
    """Load and parse all YAML skill definitions from the definitions directory.

    Returns a list sorted by filename. Raises SkillLoadError on any file-level issue.
    Does NOT validate cross-file rules (use validate_skill_definition_set for that).
    """
    target_dir = definitions_dir or _DEFINITIONS_DIR

    if not target_dir.is_dir():
        raise SkillLoadError(
            str(target_dir), "定义目录不存在或不是目录"
        )

    yaml_files = _collect_yaml_files(target_dir)
    if not yaml_files:
        return []

    results: list[LoadedSkillDefinition] = []
    for file_path in yaml_files:
        loaded = _parse_single_file(file_path)
        results.append(loaded)

    return results
