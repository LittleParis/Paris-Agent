"""User-scoped long-term memory persistence."""

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_memory import AgentMemory


def _encode_cursor(updated_at: datetime, memory_id: uuid.UUID) -> str:
    payload = json.dumps(
        {
            "updated_at": updated_at.isoformat(),
            "memory_id": str(memory_id),
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        return (
            datetime.fromisoformat(payload["updated_at"]),
            uuid.UUID(payload["memory_id"]),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid memory cursor") from exc


class MemoryRepository:
    """Persist memories without deciding domain policy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        memory_type: str,
        scope: str,
        content: str,
        summary: str | None,
        importance: Decimal,
        confidence: Decimal,
        source_type: str,
        source_id: uuid.UUID | None,
        source_detail: dict,
        tags: list[str],
        content_hash: str,
        expires_at: datetime | None,
    ) -> AgentMemory:
        now = datetime.now(UTC)
        memory = AgentMemory(
            memory_id=uuid.uuid4(),
            user_id=user_id,
            project_id=project_id,
            memory_type=memory_type,
            scope=scope,
            content=content,
            summary=summary,
            importance=importance,
            confidence=confidence,
            source_type=source_type,
            source_id=source_id,
            source_detail=source_detail,
            tags=tags,
            content_hash=content_hash,
            version=1,
            access_count=0,
            sync_status="not_indexed",
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self.session.add(memory)
        await self.session.flush()
        await self.session.refresh(memory)
        return memory

    async def get_owned(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> AgentMemory | None:
        stmt = select(AgentMemory).where(
            AgentMemory.memory_id == memory_id,
            AgentMemory.user_id == user_id,
        )
        if not include_deleted:
            stmt = stmt.where(AgentMemory.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active_duplicate(
        self,
        *,
        user_id: uuid.UUID,
        scope: str,
        project_id: uuid.UUID | None,
        memory_type: str,
        content_hash: str,
        exclude_memory_id: uuid.UUID | None = None,
    ) -> AgentMemory | None:
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.scope == scope,
            AgentMemory.memory_type == memory_type,
            AgentMemory.content_hash == content_hash,
            AgentMemory.deleted_at.is_(None),
        )
        if project_id is None:
            stmt = stmt.where(AgentMemory.project_id.is_(None))
        else:
            stmt = stmt.where(AgentMemory.project_id == project_id)
        if exclude_memory_id is not None:
            stmt = stmt.where(AgentMemory.memory_id != exclude_memory_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        *,
        user_id: uuid.UUID,
        memory_type: str | None,
        scope: str | None,
        project_id: uuid.UUID | None,
        tag: str | None,
        include_expired: bool,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[AgentMemory], str | None]:
        now = datetime.now(UTC)
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.deleted_at.is_(None),
        )
        if not include_expired:
            stmt = stmt.where(
                or_(
                    AgentMemory.expires_at.is_(None),
                    AgentMemory.expires_at > now,
                )
            )
        if memory_type is not None:
            stmt = stmt.where(AgentMemory.memory_type == memory_type)
        if scope is not None:
            stmt = stmt.where(AgentMemory.scope == scope)
        if project_id is not None:
            stmt = stmt.where(AgentMemory.project_id == project_id)
        if tag is not None:
            # Push tag filtering to SQL level for correct cursor pagination.
            from sqlalchemy import text as sql_text

            dialect = self.session.bind.dialect.name
            if dialect == "postgresql":
                stmt = stmt.where(
                    AgentMemory.tags.op("@>")(
                        sql_text("CAST(:tag_json AS jsonb)")
                    )
                ).params(tag_json=f'["{tag}"]')
            else:
                stmt = stmt.where(
                    sql_text(
                        "EXISTS (SELECT 1 FROM json_each(agent_memories.tags) "
                        "WHERE json_each.value = :tag)"
                    )
                ).params(tag=tag)
        if cursor is not None:
            cursor_time, cursor_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    AgentMemory.updated_at < cursor_time,
                    and_(
                        AgentMemory.updated_at == cursor_time,
                        AgentMemory.memory_id > cursor_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            AgentMemory.updated_at.desc(),
            AgentMemory.memory_id.asc(),
        )
        # Fetch limit + 1 to detect next page after SQL-level filtering.
        stmt = stmt.limit(limit + 1)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = _encode_cursor(last.updated_at, last.memory_id)
        return page, next_cursor

    async def search_candidates(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None,
        memory_types: list[str],
        tags: list[str],
        limit: int = 50,
    ) -> list[AgentMemory]:
        now = datetime.now(UTC)
        scope_filter = AgentMemory.scope == "user"
        if project_id is not None:
            scope_filter = or_(
                AgentMemory.scope == "user",
                and_(
                    AgentMemory.scope == "project",
                    AgentMemory.project_id == project_id,
                ),
            )
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.deleted_at.is_(None),
            or_(
                AgentMemory.expires_at.is_(None),
                AgentMemory.expires_at > now,
            ),
            scope_filter,
        )
        if memory_types:
            stmt = stmt.where(AgentMemory.memory_type.in_(memory_types))
        stmt = stmt.order_by(
            AgentMemory.importance.desc(),
            AgentMemory.updated_at.desc(),
        ).limit(limit)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if tags:
            required = set(tags)
            rows = [
                memory
                for memory in rows
                if required.issubset(set(memory.tags))
            ]
        return rows

    async def update_owned_with_version(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        expected_version: int,
        values: dict,
    ) -> AgentMemory | None:
        """Update a memory row with optimistic locking.

        Returns the updated ``AgentMemory`` on success, or ``None`` when
        the version check failed or the row was not found.  Uses
        ``RETURNING`` (PostgreSQL / SQLite 3.35+) to avoid an extra
        SELECT round trip.
        """

        values = {
            **values,
            "version": AgentMemory.version + 1,
            "updated_at": datetime.now(UTC),
        }
        result = await self.session.execute(
            update(AgentMemory)
            .where(
                AgentMemory.memory_id == memory_id,
                AgentMemory.user_id == user_id,
                AgentMemory.version == expected_version,
                AgentMemory.deleted_at.is_(None),
            )
            .values(**values)
            .returning(AgentMemory)
        )
        return result.scalar_one_or_none()

    async def soft_delete_owned_with_version(
        self,
        *,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        expected_version: int,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(AgentMemory)
            .where(
                AgentMemory.memory_id == memory_id,
                AgentMemory.user_id == user_id,
                AgentMemory.version == expected_version,
                AgentMemory.deleted_at.is_(None),
            )
            .values(
                deleted_at=now,
                updated_at=now,
                version=AgentMemory.version + 1,
            )
        )
        return result.rowcount == 1

    async def touch_access_batch(
        self,
        *,
        user_id: uuid.UUID,
        memory_ids: list[uuid.UUID],
    ) -> None:
        if not memory_ids:
            return
        await self.session.execute(
            update(AgentMemory)
            .where(
                AgentMemory.user_id == user_id,
                AgentMemory.memory_id.in_(memory_ids),
                AgentMemory.deleted_at.is_(None),
            )
            .values(
                access_count=AgentMemory.access_count + 1,
                last_accessed_at=datetime.now(UTC),
            )
        )
