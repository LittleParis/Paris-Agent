import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
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


# ---------------------------------------------------------------------------
# W1 fix: Extract user_id from the X-User-Id header, falling back to the
# configured default user so that tests / local dev still work.
# ---------------------------------------------------------------------------
async def resolve_user_id(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> uuid.UUID:
    if x_user_id:
        try:
            return uuid.UUID(x_user_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_header", "message": "X-User-Id is not a valid UUID"},
            ) from exc
    return get_settings().default_user_id


UserId = Annotated[uuid.UUID, Depends(resolve_user_id)]


# ---------------------------------------------------------------------------
# Shared 409 helper – used by create / update / delete for consistency (W2).
# ---------------------------------------------------------------------------
def conflict_response(exc: Exception, memory_id: uuid.UUID | None = None) -> JSONResponse:
    body: dict = {"detail": str(exc)}
    if memory_id is not None:
        body["memory_id"] = str(memory_id)
    if isinstance(exc, MemoryVersionConflictError):
        body["current_version"] = exc.current_version
    return JSONResponse(status_code=409, content=body)


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate,
    session: SessionDependency,
    user_id: UserId,
) -> MemoryRead | JSONResponse:
    try:
        memory = await MemoryManager(session).create_manual(
            user_id=user_id,
            payload=payload,
        )
        return MemoryRead.model_validate(memory)
    except DuplicateMemoryError as exc:
        return conflict_response(exc, exc.memory_id)


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    session: SessionDependency,
    user_id: UserId,
    memory_type: str | None = None,
    scope: str | None = None,
    project_id: uuid.UUID | None = None,
    tag: str | None = None,
    include_expired: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> MemoryListResponse:
    try:
        rows, next_cursor = await MemoryRepository(session).list_owned(
            user_id=user_id,
            memory_type=memory_type,
            scope=scope,
            project_id=project_id,
            tag=tag,
            include_expired=include_expired,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        # W6: invalid cursor → 400 instead of unhandled 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MemoryListResponse(
        items=[MemoryRead.model_validate(row) for row in rows],
        next_cursor=next_cursor,
    )


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    payload: MemorySearchRequest,
    session: SessionDependency,
    user_id: UserId,
) -> MemorySearchResponse:
    repo = MemoryRepository(session)
    hits = await MemoryRetriever(
        repository=repo
    ).search(
        user_id=user_id,
        query=payload.query,
        project_id=payload.project_id,
        memory_types=payload.memory_types,
        tags=payload.tags,
        limit=payload.limit,
        touch_access=False,
    )
    # Commit any session-level changes (none expected with touch_access=False,
    # but keeps the contract explicit).
    await session.commit()
    return MemorySearchResponse(items=hits)


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(
    memory_id: uuid.UUID,
    session: SessionDependency,
    user_id: UserId,
) -> MemoryRead:
    try:
        memory = await MemoryManager(session).get(
            memory_id=memory_id,
            user_id=user_id,
        )
        return MemoryRead.model_validate(memory)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc


@router.patch("/{memory_id}", response_model=MemoryRead)
async def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
    session: SessionDependency,
    user_id: UserId,
) -> MemoryRead | JSONResponse:
    try:
        memory = await MemoryManager(session).update(
            memory_id=memory_id,
            user_id=user_id,
            payload=payload,
        )
        return MemoryRead.model_validate(memory)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    except DuplicateMemoryError as exc:
        return conflict_response(exc, exc.memory_id)
    except MemoryVersionConflictError as exc:
        return conflict_response(exc, memory_id)
    except ValueError as exc:
        # W6: domain validation errors → 422 instead of unhandled 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_memory(
    memory_id: uuid.UUID,
    session: SessionDependency,
    user_id: UserId,
    version: Annotated[int, Query(ge=1)],
) -> Response:
    try:
        await MemoryManager(session).delete(
            memory_id=memory_id,
            user_id=user_id,
            version=version,
        )
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    except MemoryVersionConflictError as exc:
        # W2 fix: consistent 409 format across update and delete.
        return conflict_response(exc, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
