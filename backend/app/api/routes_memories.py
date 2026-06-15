import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repositories.memories import MemoryRepository
from app.db.session import get_session
from app.memory.manager import (
    DuplicateMemoryError,
    MemoryManager,
    MemoryNotFoundError,
    MemoryVersionConflictError,
)
from app.memory.retriever import MemoryRetriever
from app.schemas.memory import (
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryUpdate,
)

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def conflict_response(exc: Exception, memory_id: uuid.UUID) -> JSONResponse:
    body = {"detail": str(exc), "memory_id": str(memory_id)}
    if isinstance(exc, MemoryVersionConflictError):
        body["current_version"] = exc.current_version
    return JSONResponse(status_code=409, content=body)


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate,
    session: SessionDependency,
) -> MemoryRead | JSONResponse:
    try:
        memory = await MemoryManager(session).create_manual(
            user_id=get_settings().default_user_id,
            payload=payload,
        )
        return MemoryRead.model_validate(memory)
    except DuplicateMemoryError as exc:
        return conflict_response(exc, exc.memory_id)


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    session: SessionDependency,
    memory_type: str | None = None,
    scope: str | None = None,
    project_id: uuid.UUID | None = None,
    tag: str | None = None,
    include_expired: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> MemoryListResponse:
    rows, next_cursor = await MemoryRepository(session).list_owned(
        user_id=get_settings().default_user_id,
        memory_type=memory_type,
        scope=scope,
        project_id=project_id,
        tag=tag,
        include_expired=include_expired,
        limit=limit,
        cursor=cursor,
    )
    return MemoryListResponse(
        items=[MemoryRead.model_validate(row) for row in rows],
        next_cursor=next_cursor,
    )


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    payload: MemorySearchRequest,
    session: SessionDependency,
) -> MemorySearchResponse:
    hits = await MemoryRetriever(
        repository=MemoryRepository(session)
    ).search(
        user_id=get_settings().default_user_id,
        query=payload.query,
        project_id=payload.project_id,
        memory_types=payload.memory_types,
        tags=payload.tags,
        limit=payload.limit,
        touch_access=False,
    )
    return MemorySearchResponse(items=hits)


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(
    memory_id: uuid.UUID,
    session: SessionDependency,
) -> MemoryRead:
    try:
        memory = await MemoryManager(session).get(
            memory_id=memory_id,
            user_id=get_settings().default_user_id,
        )
        return MemoryRead.model_validate(memory)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc


@router.patch("/{memory_id}", response_model=MemoryRead)
async def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
    session: SessionDependency,
) -> MemoryRead | JSONResponse:
    try:
        memory = await MemoryManager(session).update(
            memory_id=memory_id,
            user_id=get_settings().default_user_id,
            payload=payload,
        )
        return MemoryRead.model_validate(memory)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    except DuplicateMemoryError as exc:
        return conflict_response(exc, exc.memory_id)
    except MemoryVersionConflictError as exc:
        return conflict_response(exc, memory_id)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_memory(
    memory_id: uuid.UUID,
    session: SessionDependency,
    version: Annotated[int, Query(ge=1)],
) -> None:
    try:
        await MemoryManager(session).delete(
            memory_id=memory_id,
            user_id=get_settings().default_user_id,
            version=version,
        )
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    except MemoryVersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "current_version": exc.current_version},
        ) from exc
