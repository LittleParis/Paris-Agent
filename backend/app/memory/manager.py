"""Long-term memory lifecycle orchestration."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_memory import AgentMemory
from app.db.repositories.memories import MemoryRepository
from app.memory.deduplicator import compute_content_hash
from app.schemas.memory import (
    ConsolidationMemoryCommand,
    MemoryCreate,
    MemoryRead,
    MemoryUpdate,
    MemoryWriteResult,
)


class MemoryDomainError(Exception):
    """Base memory domain error."""


class MemoryNotFoundError(MemoryDomainError):
    """The owned active memory does not exist."""


class DuplicateMemoryError(MemoryDomainError):
    """An active exact duplicate exists."""

    def __init__(self, memory_id: uuid.UUID) -> None:
        self.memory_id = memory_id
        super().__init__("An active duplicate memory already exists.")


class MemoryVersionConflictError(MemoryDomainError):
    """The optimistic-lock version is stale."""

    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__("Memory version conflict.")


def _content_hash(
    *,
    memory_type: str,
    scope: str,
    project_id: uuid.UUID | None,
    content: str,
) -> str:
    return compute_content_hash(
        memory_type=memory_type,
        scope=scope,
        project_id=project_id,
        content=content,
    )


class MemoryManager:
    """The only write entry point for memory lifecycle changes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MemoryRepository(session)

    async def get(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AgentMemory:
        memory = await self.repository.get_owned(memory_id, user_id)
        if memory is None:
            raise MemoryNotFoundError
        return memory

    async def create_manual(
        self,
        *,
        user_id: uuid.UUID,
        payload: MemoryCreate,
    ) -> AgentMemory:
        content_hash = _content_hash(
            memory_type=payload.memory_type,
            scope=payload.scope,
            project_id=payload.project_id,
            content=payload.content,
        )
        duplicate = await self.repository.find_active_duplicate(
            user_id=user_id,
            scope=payload.scope,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            content_hash=content_hash,
        )
        if duplicate is not None:
            raise DuplicateMemoryError(duplicate.memory_id)
        memory = await self.repository.create(
            user_id=user_id,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            scope=payload.scope,
            content=payload.content,
            summary=payload.summary,
            importance=payload.importance,
            confidence=payload.confidence,
            source_type="manual",
            source_id=None,
            source_detail={"created_via": "memory_api"},
            tags=payload.tags,
            content_hash=content_hash,
            expires_at=payload.expires_at,
        )
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def create_consolidated(
        self,
        *,
        user_id: uuid.UUID,
        run_id: uuid.UUID,
        skill_version: str,
        payload: ConsolidationMemoryCommand | MemoryCreate,
    ) -> MemoryWriteResult:
        content_hash = _content_hash(
            memory_type=payload.memory_type,
            scope=payload.scope,
            project_id=payload.project_id,
            content=payload.content,
        )
        duplicate = await self.repository.find_active_duplicate(
            user_id=user_id,
            scope=payload.scope,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            content_hash=content_hash,
        )
        if duplicate is not None:
            return MemoryWriteResult(
                memory=MemoryRead.model_validate(duplicate),
                created=False,
                deduplicated=True,
            )
        memory = await self.repository.create(
            user_id=user_id,
            project_id=payload.project_id,
            memory_type=payload.memory_type,
            scope=payload.scope,
            content=payload.content,
            summary=payload.summary,
            importance=payload.importance,
            confidence=payload.confidence,
            source_type="consolidation",
            source_id=run_id,
            source_detail={
                **getattr(payload, "source_detail", {}),
                "skill_id": "memory_consolidation",
                "skill_version": skill_version,
                "extractor": "deterministic_v1",
            },
            tags=payload.tags,
            content_hash=content_hash,
            expires_at=payload.expires_at,
        )
        await self.session.commit()
        await self.session.refresh(memory)
        return MemoryWriteResult(
            memory=MemoryRead.model_validate(memory),
            created=True,
            deduplicated=False,
        )

    async def update(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: MemoryUpdate,
    ) -> AgentMemory:
        current = await self.get(memory_id=memory_id, user_id=user_id)
        if current.version != payload.version:
            raise MemoryVersionConflictError(current.version)

        values = payload.model_dump(
            exclude={"version"},
            exclude_unset=True,
        )
        merged = {
            "memory_type": values.get("memory_type", current.memory_type),
            "scope": values.get("scope", current.scope),
            "project_id": (
                values["project_id"]
                if "project_id" in values
                else current.project_id
            ),
            "content": values.get("content", current.content),
        }
        if merged["scope"] == "user" and merged["project_id"] is not None:
            raise ValueError("project_id must be null for user scope")
        if merged["scope"] == "project" and merged["project_id"] is None:
            raise ValueError("project_id is required for project scope")
        if (
            merged["memory_type"] == "project"
            and merged["scope"] != "project"
        ):
            raise ValueError("project memories must use project scope")

        content_hash = _content_hash(**merged)
        duplicate = await self.repository.find_active_duplicate(
            user_id=user_id,
            scope=merged["scope"],
            project_id=merged["project_id"],
            memory_type=merged["memory_type"],
            content_hash=content_hash,
            exclude_memory_id=memory_id,
        )
        if duplicate is not None:
            raise DuplicateMemoryError(duplicate.memory_id)
        values["content_hash"] = content_hash
        updated = await self.repository.update_owned_with_version(
            memory_id=memory_id,
            user_id=user_id,
            expected_version=payload.version,
            values=values,
        )
        if not updated:
            latest = await self.repository.get_owned(memory_id, user_id)
            if latest is None:
                raise MemoryNotFoundError
            raise MemoryVersionConflictError(latest.version)
        await self.session.commit()
        memory = await self.repository.get_owned(memory_id, user_id)
        if memory is None:
            raise MemoryNotFoundError
        return memory

    async def delete(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        version: int,
    ) -> None:
        current = await self.get(memory_id=memory_id, user_id=user_id)
        if current.version != version:
            raise MemoryVersionConflictError(current.version)
        deleted = await self.repository.soft_delete_owned_with_version(
            memory_id=memory_id,
            user_id=user_id,
            expected_version=version,
        )
        if not deleted:
            latest = await self.repository.get_owned(memory_id, user_id)
            if latest is None:
                raise MemoryNotFoundError
            raise MemoryVersionConflictError(latest.version)
        await self.session.commit()
