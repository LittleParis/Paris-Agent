"""Skill / SkillVersion / SkillRun 数据访问层。

路由、同步器和 Runner 不直接拼接 SQL。后续增加事务、锁或查询优化时，
只需集中修改 Repository，而不改变 API 契约。

三个 Repository 分别对应 Skill Registry 的三张核心表：
  - SkillRepository         → agent_skills（Skill 元信息）
  - SkillVersionRepository  → agent_skill_versions（版本快照）
  - AgentSkillRunRepository → agent_skill_runs（Run 与版本的绑定记录）
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_skill import AgentSkill
from app.db.models.agent_skill_version import AgentSkillVersion
from app.db.models.agent_skill_run import AgentSkillRun


# ---------------------------------------------------------------------------
# SkillRepository
# ---------------------------------------------------------------------------


class SkillRepository:
    """封装 agent_skills 表的读写操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_skill_id(self, skill_id: str) -> AgentSkill | None:
        """通过业务标识 skill_id 查询 Skill 记录。"""

        result = await self.session.execute(
            select(AgentSkill).where(AgentSkill.skill_id == skill_id)
        )
        return result.scalar_one_or_none()

    async def list(self, *, include_disabled: bool = False) -> list[AgentSkill]:
        """列出 Skill，按 enabled DESC → name ASC → skill_id ASC 排序。

        include_disabled=False 时仅返回 enabled=True 的 Skill。
        is_default 标记由 Registry Service 层解析，此处不做处理。
        """

        stmt = select(AgentSkill)
        if not include_disabled:
            stmt = stmt.where(AgentSkill.enabled == True)  # noqa: E712
        stmt = stmt.order_by(
            AgentSkill.enabled.desc(),
            AgentSkill.name.asc(),
            AgentSkill.skill_id.asc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_metadata(
        self,
        skill_id: str,
        *,
        name: str,
        description: str,
        enabled: bool,
    ) -> AgentSkill:
        """按 skill_id 存在则更新元信息，不存在则新建。

        仅 flush，不 commit —— 事务由同步器（Synchronizer）统一管理。
        """

        result = await self.session.execute(
            select(AgentSkill).where(AgentSkill.skill_id == skill_id)
        )
        skill = result.scalar_one_or_none()

        if skill is not None:
            skill.name = name
            skill.description = description
            skill.enabled = enabled
        else:
            skill = AgentSkill(
                skill_id=skill_id,
                name=name,
                description=description,
                enabled=enabled,
            )
            self.session.add(skill)

        await self.session.flush()
        await self.session.refresh(skill)
        return skill

    async def set_default_version(self, skill_id: str, version_id: int) -> None:
        """更新 Skill 的 default_version_id，指向当前生效版本。

        仅 flush，不 commit —— 事务由同步器统一管理。
        """

        result = await self.session.execute(
            select(AgentSkill).where(AgentSkill.skill_id == skill_id)
        )
        skill = result.scalar_one_or_none()
        if skill is not None:
            skill.default_version_id = version_id
            await self.session.flush()

    async def disable_skill(self, skill_id: str) -> None:
        """将 Skill 标记为禁用（enabled=False）。

        仅 flush，不 commit —— 事务由同步器统一管理。
        """

        result = await self.session.execute(
            select(AgentSkill).where(AgentSkill.skill_id == skill_id)
        )
        skill = result.scalar_one_or_none()
        if skill is not None:
            skill.enabled = False
            await self.session.flush()


# ---------------------------------------------------------------------------
# SkillVersionRepository
# ---------------------------------------------------------------------------


class SkillVersionRepository:
    """封装 agent_skill_versions 表的读写操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_skill_and_version(
        self, agent_skill_id: int, version: str
    ) -> AgentSkillVersion | None:
        """通过 (agent_skill_id, version) 复合键查询版本记录。"""

        result = await self.session.execute(
            select(AgentSkillVersion).where(
                AgentSkillVersion.agent_skill_id == agent_skill_id,
                AgentSkillVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, version_db_id: int) -> AgentSkillVersion | None:
        """通过内部自增主键查询版本记录。"""

        result = await self.session.execute(
            select(AgentSkillVersion).where(
                AgentSkillVersion.id == version_db_id
            )
        )
        return result.scalar_one_or_none()

    async def create_immutable(
        self,
        *,
        version_id: uuid.UUID,
        agent_skill_id: int,
        version: str,
        definition_snapshot: dict,
        content_hash: str,
        source_path: str,
    ) -> AgentSkillVersion:
        """创建不可变版本记录。

        仅 flush，不 commit —— 事务由同步器统一管理。
        """

        ver = AgentSkillVersion(
            version_id=version_id,
            agent_skill_id=agent_skill_id,
            version=version,
            definition_snapshot=definition_snapshot,
            content_hash=content_hash,
            source_path=source_path,
        )
        self.session.add(ver)
        await self.session.flush()
        await self.session.refresh(ver)
        return ver


# ---------------------------------------------------------------------------
# AgentSkillRunRepository
# ---------------------------------------------------------------------------


class AgentSkillRunRepository:
    """封装 agent_skill_runs 表的读写操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_binding(
        self,
        *,
        skill_run_id: uuid.UUID,
        run_id: uuid.UUID,
        skill_version_id: int,
        selection_mode: str,
        definition_snapshot: dict,
    ) -> AgentSkillRun:
        """创建 Run 与 Skill Version 的绑定记录。

        仅 flush，不 commit —— 事务由调用方（Runner）统一管理。
        """

        binding = AgentSkillRun(
            skill_run_id=skill_run_id,
            run_id=run_id,
            skill_version_id=skill_version_id,
            selection_mode=selection_mode,
            definition_snapshot=definition_snapshot,
        )
        self.session.add(binding)
        await self.session.flush()
        await self.session.refresh(binding)
        return binding

    async def get_by_run_id(self, run_id: uuid.UUID) -> AgentSkillRun | None:
        """通过 run_id 查询 Skill Run 绑定记录。"""

        result = await self.session.execute(
            select(AgentSkillRun).where(
                AgentSkillRun.run_id == run_id
            )
        )
        return result.scalar_one_or_none()
