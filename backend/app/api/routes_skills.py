"""Skill Registry HTTP 路由。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.skills.registry import skill_registry, SkillRegistryNotReadyError
from app.schemas.skill import SkillDetail, SkillListItem


router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("", response_model=list[SkillListItem])
async def list_skills(
    include_disabled: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> list[SkillListItem]:
    """List published skills. Default skill first, then by name."""
    try:
        return await skill_registry.list_skills(
            session, include_disabled=include_disabled
        )
    except SkillRegistryNotReadyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Skill Registry is not ready. The application may have failed during startup.",
        )


@router.get("/{skill_id}", response_model=SkillDetail)
async def get_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),
) -> SkillDetail:
    """Get skill detail. Unknown skill returns 404."""
    try:
        detail = await skill_registry.get_skill(session, skill_id)
    except SkillRegistryNotReadyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Skill Registry is not ready.",
        )
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return detail
