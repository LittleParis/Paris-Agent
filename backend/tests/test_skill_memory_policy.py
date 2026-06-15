import pytest
from pydantic import ValidationError

from app.schemas.skill import SkillDefinition, SkillMemoryPolicy
from app.skills.loader import load_all_skill_definitions


def test_write_requires_read() -> None:
    with pytest.raises(ValidationError, match="write requires read"):
        SkillMemoryPolicy(read=False, write=True)


def test_only_memory_consolidation_can_write() -> None:
    definitions = {
        item.definition.skill_id: item.definition
        for item in load_all_skill_definitions()
    }

    assert definitions["tech_qa"].memory_policy.model_dump() == {
        "read": True,
        "write": False,
    }
    assert definitions["learning_path"].memory_policy.read is True
    assert definitions["project_summary"].memory_policy.read is True
    assert definitions["memory_consolidation"].memory_policy.model_dump() == {
        "read": True,
        "write": True,
    }
    assert all(
        not definition.memory_policy.write
        for skill_id, definition in definitions.items()
        if skill_id != "memory_consolidation"
    )


def test_non_consolidation_definition_cannot_enable_write() -> None:
    definition = next(
        item.definition
        for item in load_all_skill_definitions()
        if item.definition.skill_id == "tech_qa"
    )
    data = definition.model_dump()
    data["memory_policy"] = {"read": True, "write": True}

    with pytest.raises(ValidationError, match="memory_consolidation"):
        SkillDefinition.model_validate(data)
