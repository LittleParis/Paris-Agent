"""Skill Registry Service — 从数据库读取已发布的 Skill 定义。"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.skills import SkillRepository, SkillVersionRepository
from app.schemas.skill import SkillDetail, SkillListItem


logger = logging.getLogger(__name__)


class SkillRegistryNotReadyError(Exception):
    """Registry 尚未完成初始化。"""
    pass


class SkillRegistryService:
    """Skill Registry 查询服务。以数据库为运行时读取来源。"""

    def __init__(self) -> None:
        self._ready: bool = False

    @property
    def ready(self) -> bool:
        return self._ready

    def mark_ready(self) -> None:
        self._ready = True
        logger.info("Skill Registry is ready.")

    def _ensure_ready(self) -> None:
        if not self._ready:
            raise SkillRegistryNotReadyError(
                "Skill Registry has not been initialized. "
                "The application may have failed during startup."
            )

    async def list_skills(
        self,
        session: AsyncSession,
        *,
        include_disabled: bool = False,
    ) -> list[SkillListItem]:
        """List published skills. Default skill first, then by name/skill_id."""
        self._ensure_ready()
        skill_repo = SkillRepository(session)
        version_repo = SkillVersionRepository(session)
        
        skills = await skill_repo.list(include_disabled=include_disabled)
        items: list[SkillListItem] = []
        
        for skill in skills:
            # Get the default version to extract version string and is_default
            version_str = ""
            is_default = False
            
            if skill.default_version_id is not None:
                version = await version_repo.get_by_id(skill.default_version_id)
                if version is not None:
                    version_str = version.version
                    # Check if this is the default skill by reading the snapshot
                    snapshot = version.definition_snapshot
                    if isinstance(snapshot, dict):
                        is_default = snapshot.get("is_default", False)
            
            items.append(SkillListItem(
                skill_id=skill.skill_id,
                name=skill.name,
                description=skill.description,
                enabled=skill.enabled,
                version=version_str,
                is_default=is_default,
            ))
        
        # Sort: default skill first, then by name, then by skill_id
        items.sort(key=lambda item: (not item.is_default, item.name, item.skill_id))
        return items

    async def get_skill(
        self,
        session: AsyncSession,
        skill_id: str,
    ) -> SkillDetail | None:
        """Get skill detail by skill_id. Returns None if not found.
        
        Can read disabled skills for diagnostics.
        Does NOT return prompt, content_hash, source_path, or internal IDs.
        """
        self._ensure_ready()
        skill_repo = SkillRepository(session)
        version_repo = SkillVersionRepository(session)
        
        skill = await skill_repo.get_by_skill_id(skill_id)
        if skill is None:
            return None
        
        if skill.default_version_id is None:
            # Skill exists but has no published version
            return None
        
        version = await version_repo.get_by_id(skill.default_version_id)
        if version is None:
            return None
        
        snapshot = version.definition_snapshot
        if not isinstance(snapshot, dict):
            return None
        
        is_default = snapshot.get("is_default", False)
        
        return SkillDetail(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            enabled=skill.enabled,
            version=version.version,
            is_default=is_default,
            input_schema=snapshot.get("input_schema", {}),
            output_schema=snapshot.get("output_schema", {}),
            tools=snapshot.get("tools", []),
            workflow=snapshot.get("workflow", {}),
            memory_policy=snapshot.get("memory_policy", {}),
            safety_policy=snapshot.get("safety_policy", {}),
            runtime_config=snapshot.get("runtime_config", {}),
        )

    async def resolve_default_skill_version(
        self,
        session: AsyncSession,
    ):
        """Resolve the system default skill (tech_qa) and its current version.
        
        Returns (skill, version, definition_snapshot) or raises SkillRegistryNotReadyError.
        Used internally by SkillSelectionService.
        """
        self._ensure_ready()
        from app.db.models.agent_skill import AgentSkill
        from app.db.models.agent_skill_version import AgentSkillVersion
        from sqlalchemy import select
        
        skill_repo = SkillRepository(session)
        version_repo = SkillVersionRepository(session)
        
        skill = await skill_repo.get_by_skill_id("tech_qa")
        if skill is None or not skill.enabled or skill.default_version_id is None:
            raise SkillRegistryNotReadyError(
                "Default skill 'tech_qa' is not available, not enabled, "
                "or has no published version."
            )
        
        version = await version_repo.get_by_id(skill.default_version_id)
        if version is None:
            raise SkillRegistryNotReadyError(
                "Default skill version not found."
            )
        
        return skill, version, version.definition_snapshot


# Module-level singleton
skill_registry = SkillRegistryService()
