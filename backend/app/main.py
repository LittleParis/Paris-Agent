"""Paris Agent FastAPI 应用入口。

P5: 增加 lifespan 启动阶段 Skill 定义同步。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_agent import router as agent_router
from app.api.routes_health import router as health_router
from app.api.routes_memories import router as memories_router
from app.api.routes_skills import router as skills_router
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.skills.loader import load_all_skill_definitions, SkillLoadError
from app.skills.validator import validate_skill_definition_set, SkillValidationError
from app.skills.synchronizer import sync_skill_definitions, SkillSyncError
from app.skills.registry import skill_registry


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: sync skill definitions on startup."""
    # ---- Startup ----
    logger.info("Loading skill definitions...")
    try:
        definitions = load_all_skill_definitions()
        logger.info("Loaded %d skill definitions.", len(definitions))
        
        validate_skill_definition_set(definitions)
        logger.info("Skill definition set validated.")
        
        async with async_session_factory() as session:
            await sync_skill_definitions(session, definitions)
        logger.info("Skill definitions synced to database.")
        
        skill_registry.mark_ready()
    except (SkillLoadError, SkillValidationError, SkillSyncError) as exc:
        logger.critical("Skill Registry startup failed: %s", exc)
        raise
    except Exception as exc:
        logger.critical("Unexpected error during skill sync: %s", exc)
        raise
    
    yield
    
    # ---- Shutdown ----
    logger.info("Application shutting down.")


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Skill-based Agent Workbench backend.",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(agent_router)
app.include_router(skills_router)
app.include_router(memories_router)
