"""Skill Selection Service — 处理显式选择和默认选择。"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.skills import SkillRepository, SkillVersionRepository
from app.skills.registry import skill_registry, SkillRegistryNotReadyError


logger = logging.getLogger(__name__)


class SkillSelectionError(Exception):
    """Skill 选择失败 — 拒绝创建 Run。"""
    pass


class SkillSelectionResult:
    """Skill 选择结果。"""
    def __init__(
        self,
        *,
        skill,           # AgentSkill model
        skill_version,   # AgentSkillVersion model
        selection_mode: str,  # "explicit" or "default"
        definition_snapshot: dict,
    ) -> None:
        self.skill = skill
        self.skill_version = skill_version
        self.selection_mode = selection_mode
        self.definition_snapshot = definition_snapshot


async def select_skill(
    session: AsyncSession,
    requested_skill_id: str | None,
) -> SkillSelectionResult:
    """Select a skill for a new Run.
    
    Rules:
    - requested_skill_id provided: explicit selection, skill must exist and be enabled
    - requested_skill_id is None: default selection (tech_qa)
    - Unknown or disabled skill: raise SkillSelectionError
    - Default skill not available: raise SkillRegistryNotReadyError
    """
    skill_registry._ensure_ready()
    
    skill_repo = SkillRepository(session)
    version_repo = SkillVersionRepository(session)
    
    if requested_skill_id is not None:
        # Explicit selection
        skill = await skill_repo.get_by_skill_id(requested_skill_id)
        if skill is None:
            raise SkillSelectionError(
                f"Unknown skill: '{requested_skill_id}'"
            )
        if not skill.enabled:
            raise SkillSelectionError(
                f"Skill '{requested_skill_id}' is disabled"
            )
        if skill.default_version_id is None:
            raise SkillSelectionError(
                f"Skill '{requested_skill_id}' has no published version"
            )
        
        version = await version_repo.get_by_id(skill.default_version_id)
        if version is None:
            raise SkillSelectionError(
                f"Skill '{requested_skill_id}' default version not found"
            )
        
        return SkillSelectionResult(
            skill=skill,
            skill_version=version,
            selection_mode="explicit",
            definition_snapshot=version.definition_snapshot,
        )
    else:
        # Default selection: tech_qa
        skill, version, snapshot = await skill_registry.resolve_default_skill_version(session)
        return SkillSelectionResult(
            skill=skill,
            skill_version=version,
            selection_mode="default",
            definition_snapshot=snapshot,
        )
