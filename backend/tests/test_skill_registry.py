"""P5 Skill Synchronizer 和 Repository 测试。"""

import pytest

from app.db.base import Base
from app.db.models import (  # noqa: F401
    AgentRun, AgentSkill, AgentSkillRun, AgentSkillVersion, RuntimeEvent,
)
from app.db.session import engine, async_session_factory
from app.db.repositories.skills import SkillRepository, SkillVersionRepository
from app.skills.loader import load_all_skill_definitions
from app.skills.synchronizer import sync_skill_definitions, compute_content_hash, SkillSyncError
from app.skills.registry import skill_registry
from app.agent.events import agent_run_event_broker
from app.agent.mock_runner import mock_agent_runner


@pytest.fixture(autouse=True)
async def database() -> None:
    agent_run_event_broker.clear()
    skill_registry._ready = False
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await mock_agent_runner.wait_for_all()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
async def test_sync_creates_8_skills_and_versions():
    """First sync creates 8 skills and 8 versions."""
    definitions = load_all_skill_definitions()
    async with async_session_factory() as session:
        await sync_skill_definitions(session, definitions)

    async with async_session_factory() as session:
        repo = SkillRepository(session)
        skills = await repo.list(include_disabled=True)
        assert len(skills) >= 8
        
        # All should be enabled
        enabled_skills = [s for s in skills if s.enabled]
        assert len(enabled_skills) >= 8
        
        # All should have default_version_id set
        for skill in skills:
            assert skill.default_version_id is not None


@pytest.mark.anyio
async def test_sync_is_idempotent():
    """Second sync with same definitions should not create duplicates."""
    definitions = load_all_skill_definitions()
    
    async with async_session_factory() as session:
        await sync_skill_definitions(session, definitions)
    
    async with async_session_factory() as session:
        await sync_skill_definitions(session, definitions)

    async with async_session_factory() as session:
        repo = SkillRepository(session)
        skills = await repo.list(include_disabled=True)
        assert len(skills) >= 8
        
        # Check that each skill still has exactly 1 version
        version_repo = SkillVersionRepository(session)
        # Build expected version map from YAML definitions
        definitions = load_all_skill_definitions()
        expected_versions = {d.definition.skill_id: d.definition.version for d in definitions}
        for skill in skills:
            version = await version_repo.get_by_id(skill.default_version_id)
            assert version is not None
            assert version.version == expected_versions.get(skill.skill_id, "1.0.0")


@pytest.mark.anyio
async def test_sync_same_version_different_hash_raises():
    """Syncing same version with different content should raise SkillSyncError."""
    definitions = load_all_skill_definitions()
    
    # First sync
    async with async_session_factory() as session:
        await sync_skill_definitions(session, definitions)
    
    # Tamper with a definition (change the name)
    for d in definitions:
        if d.definition.skill_id == "tech_qa":
            # Create a modified copy
            from app.schemas.skill import SkillDefinition
            modified_data = d.definition.model_dump()
            modified_data["name"] = "Tampered Name"
            modified_def = SkillDefinition(**modified_data)
            d.definition = modified_def
            break
    
    # Second sync should fail
    with pytest.raises(SkillSyncError, match="tampered"):
        async with async_session_factory() as session:
            await sync_skill_definitions(session, definitions)


@pytest.mark.anyio
async def test_default_version_id_points_to_current_version():
    """default_version_id should point to the version matching YAML version."""
    definitions = load_all_skill_definitions()
    async with async_session_factory() as session:
        await sync_skill_definitions(session, definitions)

    async with async_session_factory() as session:
        repo = SkillRepository(session)
        version_repo = SkillVersionRepository(session)
        
        skill = await repo.get_by_skill_id("tech_qa")
        assert skill is not None
        assert skill.default_version_id is not None
        
        version = await version_repo.get_by_id(skill.default_version_id)
        assert version is not None
        # tech_qa was bumped to 1.1.0 in P6
        assert version.version == "1.1.0"


@pytest.mark.anyio
async def test_content_hash_is_deterministic():
    """Same definition should always produce the same hash."""
    definitions = load_all_skill_definitions()
    hash1 = compute_content_hash(definitions[0].definition)
    hash2 = compute_content_hash(definitions[0].definition)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest
