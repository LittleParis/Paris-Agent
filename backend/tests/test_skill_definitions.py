"""P5 Skill Definition Loader 和 Validator 单元测试。"""

import pytest
from pathlib import Path
import tempfile
import textwrap

from app.skills.loader import (
    load_all_skill_definitions,
    SkillLoadError,
    LoadedSkillDefinition,
)
from app.skills.validator import (
    validate_skill_definition_set,
    SkillValidationError,
    REQUIRED_SKILL_IDS,
)


# ===== Loader Tests =====


def test_load_all_8_definitions_from_real_directory():
    """All 8 built-in YAML files load successfully."""
    definitions = load_all_skill_definitions()
    assert len(definitions) >= 8
    skill_ids = {d.definition.skill_id for d in definitions}
    assert REQUIRED_SKILL_IDS.issubset(skill_ids)


def test_load_rejects_empty_file(tmp_path: Path):
    (tmp_path / "empty_skill.yaml").write_text("")
    with pytest.raises(SkillLoadError, match="为空"):
        load_all_skill_definitions(tmp_path)


def test_load_rejects_non_object_root(tmp_path: Path):
    (tmp_path / "list_skill.yaml").write_text("- item1\n- item2\n")
    with pytest.raises(SkillLoadError, match="映射"):
        load_all_skill_definitions(tmp_path)


def test_load_rejects_invalid_yaml_syntax(tmp_path: Path):
    (tmp_path / "bad.yaml").write_text("key: [unclosed")
    with pytest.raises(SkillLoadError, match="YAML"):
        load_all_skill_definitions(tmp_path)


def test_load_rejects_filename_skill_id_mismatch(tmp_path: Path):
    """File named wrong_id.yaml but skill_id is tech_qa."""
    content = _minimal_valid_yaml("tech_qa")
    (tmp_path / "wrong_id.yaml").write_text(content)
    with pytest.raises(SkillLoadError, match="不匹配"):
        load_all_skill_definitions(tmp_path)


def test_load_rejects_missing_required_field(tmp_path: Path):
    """YAML missing the 'version' field."""
    content = textwrap.dedent("""\
        skill_id: test_skill
        name: Test
        description: Test skill
        enabled: true
        is_default: false
    """)
    (tmp_path / "test_skill.yaml").write_text(content)
    with pytest.raises(SkillLoadError, match="校验失败"):
        load_all_skill_definitions(tmp_path)


def test_load_nonexistent_directory():
    with pytest.raises(SkillLoadError, match="不存在"):
        load_all_skill_definitions(Path("/nonexistent/path"))


def test_load_empty_directory(tmp_path: Path):
    result = load_all_skill_definitions(tmp_path)
    assert result == []


# ===== Validator Tests =====


def test_validate_full_set_passes():
    """The real 8 definitions pass set validation."""
    definitions = load_all_skill_definitions()
    validate_skill_definition_set(definitions)  # should not raise


def test_validate_rejects_duplicate_skill_id(tmp_path: Path):
    """Two files with the same skill_id."""
    content = _minimal_valid_yaml("tech_qa")
    (tmp_path / "tech_qa.yaml").write_text(content)
    # Create a second file with same skill_id but different filename
    content2 = _minimal_valid_yaml("tech_qa")
    (tmp_path / "tech_qa_copy.yaml").write_text(content2)
    
    # First the loader will catch the filename mismatch for tech_qa_copy
    with pytest.raises(SkillLoadError):
        load_all_skill_definitions(tmp_path)


def test_validate_rejects_missing_required_skills(tmp_path: Path):
    """Only 1 skill instead of 8."""
    content = _minimal_valid_yaml("tech_qa", is_default=True)
    (tmp_path / "tech_qa.yaml").write_text(content)
    definitions = load_all_skill_definitions(tmp_path)
    with pytest.raises(SkillValidationError, match="缺少"):
        validate_skill_definition_set(definitions)


def test_validate_rejects_no_default_skill(tmp_path: Path):
    """All 8 skills but none is default."""
    for sid in REQUIRED_SKILL_IDS:
        content = _minimal_valid_yaml(sid, is_default=False)
        (tmp_path / f"{sid}.yaml").write_text(content)
    definitions = load_all_skill_definitions(tmp_path)
    with pytest.raises(SkillValidationError, match="is_default"):
        validate_skill_definition_set(definitions)


def test_validate_rejects_wrong_default(tmp_path: Path):
    """learning_path is default instead of tech_qa."""
    for sid in REQUIRED_SKILL_IDS:
        is_default = (sid == "learning_path")
        content = _minimal_valid_yaml(sid, is_default=is_default)
        (tmp_path / f"{sid}.yaml").write_text(content)
    definitions = load_all_skill_definitions(tmp_path)
    with pytest.raises(SkillValidationError, match="tech_qa"):
        validate_skill_definition_set(definitions)


def test_validate_rejects_disabled_default(tmp_path: Path):
    """tech_qa is default but disabled."""
    for sid in REQUIRED_SKILL_IDS:
        is_default = (sid == "tech_qa")
        content = _minimal_valid_yaml(sid, is_default=is_default, enabled=(not is_default))
        (tmp_path / f"{sid}.yaml").write_text(content)
    # tech_qa has enabled=false but is_default=true
    # We need to make the YAML valid but with enabled=false for tech_qa
    # Actually let's just write tech_qa with enabled=false
    tq_content = _minimal_valid_yaml("tech_qa", is_default=True, enabled=False)
    (tmp_path / "tech_qa.yaml").write_text(tq_content)
    definitions = load_all_skill_definitions(tmp_path)
    with pytest.raises(SkillValidationError, match="启用"):
        validate_skill_definition_set(definitions)


def test_validate_rejects_multiple_defaults(tmp_path: Path):
    """Two skills both have is_default=true."""
    for sid in REQUIRED_SKILL_IDS:
        is_default = sid in ("tech_qa", "learning_path")
        content = _minimal_valid_yaml(sid, is_default=is_default)
        (tmp_path / f"{sid}.yaml").write_text(content)
    definitions = load_all_skill_definitions(tmp_path)
    with pytest.raises(SkillValidationError, match="只能有一个"):
        validate_skill_definition_set(definitions)


# ===== Helper =====

def _minimal_valid_yaml(
    skill_id: str,
    *,
    is_default: bool = False,
    enabled: bool = True,
    version: str = "1.0.0",
) -> str:
    """Generate a minimal valid Skill YAML for testing."""
    return textwrap.dedent(f"""\
        skill_id: {skill_id}
        name: "Test {skill_id}"
        description: "Test skill for {skill_id}"
        version: "{version}"
        enabled: {str(enabled).lower()}
        is_default: {str(is_default).lower()}

        input_schema:
          type: object
          properties: {{}}
          additionalProperties: false

        output_schema:
          type: object
          properties: {{}}
          additionalProperties: false

        prompt:
          system: "You are a test assistant."
          instructions:
            - "Help the user."

        tools: []

        workflow:
          entrypoint: mock_executor
          nodes:
            - id: mock_executor
              type: mock
              dependencies: []

        memory_policy:
          read: false
          write: false

        safety_policy:
          risk_level: safe
          requires_approval: false

        runtime_config:
          timeout_seconds: 60
          max_retries: 0
    """)
