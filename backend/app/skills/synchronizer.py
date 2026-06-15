"""Skill Synchronizer — 将校验通过的 Skill 定义集事务性同步到数据库。

启动流程中，Loader 和 Validator 完成全量加载与跨文件校验后，
由本模块在单一数据库事务内完成以下操作：

1. Upsert agent_skills 元数据（name / description / enabled）
2. 对每个定义插入新版本或验证已有版本的内容哈希
3. 设置每个 Skill 的 default_version_id 指向当前 YAML 版本
4. 将不在当前 YAML 集合中的 Skill 设为禁用
5. 统一提交事务

任何步骤失败都会阻止提交，保证数据库不出现部分发布状态。
"""

import hashlib
import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_skill import AgentSkill
from app.db.models.agent_skill_version import AgentSkillVersion
from app.db.repositories.skills import SkillRepository, SkillVersionRepository
from app.schemas.skill import SkillDefinition
from app.skills.loader import LoadedSkillDefinition


logger = logging.getLogger(__name__)


class SkillSyncError(Exception):
    """Skill 同步错误 — 阻止服务启动。

    在以下场景抛出：
    - 已发布版本的内容哈希与当前 YAML 计算结果不一致（版本被篡改）
    - 数据库操作异常（连接失败、约束冲突等）
    """
    pass


# ===================================================================
# 内容哈希
# ===================================================================


def compute_content_hash(definition: SkillDefinition) -> str:
    """将 SkillDefinition 序列化为规范 JSON 后计算 SHA-256 十六进制摘要。

    规范化规则：
    - 使用 Pydantic model_dump(mode="json") 获取 JSON 兼容字典
    - 字典 key 按字母序排序（sort_keys=True）
    - 固定分隔符（"," 和 ":"），无多余空白
    - UTF-8 编码

    不包含 source_path 等文件系统元数据，只反映定义内容本身。
    相同定义无论来自哪个文件，哈希值一定相同。
    """
    data = definition.model_dump(mode="json")
    canonical = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ===================================================================
# 事务性同步
# ===================================================================


async def sync_skill_definitions(
    session: AsyncSession,
    definitions: list[LoadedSkillDefinition],
) -> None:
    """Transactionally sync all validated skill definitions to the database.

    在 FastAPI lifespan 启动阶段调用，执行以下完整流程：

    1. 为每个定义 upsert agent_skills 元数据（name / description / enabled）
    2. 计算内容哈希，插入新版本或验证已有版本的哈希一致性
    3. 设置每个 Skill 的 default_version_id 指向当前 YAML 版本
    4. 将不在当前 YAML 集合中的 Skill 自动禁用（enabled=false）
    5. 在事务末尾统一 commit

    整个流程使用调用者传入的单一 session，保证原子性。
    任一步骤失败时 session 不会提交，由上下文管理器自动回滚。

    Args:
        session: 异步数据库 Session，由调用者管理生命周期。
        definitions: 经过 Loader 加载和 Validator 校验的完整定义集。

    Raises:
        SkillSyncError: 版本哈希不匹配（已发布版本被篡改）或数据库操作失败。
    """
    skill_repo = SkillRepository(session)
    version_repo = SkillVersionRepository(session)

    # 当前 YAML 集合中所有 skill_id 的集合，用于后续检测已移除的 Skill
    yaml_skill_ids: set[str] = {
        loaded.definition.skill_id for loaded in definitions
    }

    for loaded in definitions:
        definition = loaded.definition
        skill_id_str = definition.skill_id
        version_str = definition.version

        # ---- Step 1: Upsert agent_skills 元数据 ----
        # 如果 skill_id 已存在则更新 name / description / enabled；
        # 不存在则创建新行。
        skill = await skill_repo.upsert_metadata(
            skill_id=skill_id_str,
            name=definition.name,
            description=definition.description,
            enabled=definition.enabled,
        )

        # flush 确保新创建的 agent_skills 行获得数据库生成的自增主键 id，
        # 后续 agent_skill_versions 的外键引用依赖此 id。
        await session.flush()

        # ---- Step 2: 版本插入或哈希验证 ----
        content_hash = compute_content_hash(definition)

        existing_version = await version_repo.get_by_skill_and_version(
            skill.id, version_str,
        )

        if existing_version is None:
            # 数据库不存在该 skill_id + version 组合 → 插入新版本
            snapshot = definition.model_dump(mode="json")

            new_version = await version_repo.create_immutable(
                version_id=uuid.uuid4(),
                agent_skill_id=skill.id,
                version=version_str,
                definition_snapshot=snapshot,
                content_hash=content_hash,
                source_path=loaded.source_path,
            )

            # flush 确保新版本获得数据库生成的自增主键 id，
            # 供后续 set_default_version 引用。
            await session.flush()

            logger.info(
                "Inserted new version: %s@%s (hash=%s, source=%s)",
                skill_id_str,
                version_str,
                content_hash[:12],
                loaded.source_path,
            )

            # ---- Step 3: 设置 default_version_id ----
            # 当前 YAML 中的版本即为生效版本
            await skill_repo.set_default_version(skill_id_str, new_version.id)

        elif existing_version.content_hash == content_hash:
            # 已存在且哈希匹配 → 幂等复用，无需任何写入
            logger.info(
                "Reusing existing version: %s@%s (hash=%s)",
                skill_id_str,
                version_str,
                content_hash[:12],
            )

            # 即使版本已存在，仍确保 default_version_id 指向当前 YAML 版本。
            # 这处理了以下场景：之前同步设置了不同的 default_version_id，
            # 但 YAML 仍指向同一版本。
            await skill_repo.set_default_version(
                skill_id_str, existing_version.id,
            )

        else:
            # 已存在但哈希不匹配 → 已发布版本被篡改，阻止启动
            raise SkillSyncError(
                f"Published version {skill_id_str}@{version_str} "
                f"has been tampered. "
                f"Expected hash {existing_version.content_hash}, "
                f"got {content_hash}. "
                f"Startup aborted."
            )

    # ---- Step 4: 禁用不在当前 YAML 集合中的 Skill ----
    # 查询数据库中所有已注册的 Skill，将不在 YAML 集合中的设为禁用。
    # 历史版本和 Run 绑定记录保留，不做物理删除。
    all_skills = await skill_repo.list()
    for skill in all_skills:
        if skill.skill_id not in yaml_skill_ids:
            await skill_repo.disable_skill(skill.skill_id)
            logger.warning(
                "Disabled skill '%s' — not present in current YAML definition set.",
                skill.skill_id,
            )

    # ---- Step 5: 统一提交事务 ----
    # 所有操作成功后才提交。任一步骤抛出异常时，
    # session 的上下文管理器会自动回滚，不会留下部分发布状态。
    await session.commit()

    logger.info(
        "Skill sync completed: %d definitions synced successfully.",
        len(definitions),
    )
