from __future__ import annotations

import math
import re
import uuid
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.db.models.agent_memory import AgentMemory
from app.db.repositories.memories import MemoryRepository
from app.schemas.memory import (
    MemoryRead,
    MemoryScoreBreakdown,
    MemorySearchHit,
)

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


class MemoryRetriever:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        project_id: uuid.UUID | None,
        memory_types: list[str],
        tags: list[str],
        limit: int,
        touch_access: bool,
    ) -> list[MemorySearchHit]:
        candidates = await self.repository.search_candidates(
            user_id=user_id,
            project_id=project_id,
            memory_types=memory_types,
            tags=tags,
            limit=limit * 10,  # Fetch more candidates than needed for scoring.
        )
        now = datetime.now(UTC)
        hits = [
            self._score(
                memory=memory,
                query=query,
                project_id=project_id,
                now=now,
            )
            for memory in candidates
        ]
        hits.sort(
            key=lambda hit: (
                hit.score,
                float(hit.memory.importance),
                hit.memory.updated_at,
                str(hit.memory.memory_id),
            ),
            reverse=True,
        )
        selected = hits[:limit]
        if touch_access and selected:
            await self.repository.touch_access_batch(
                user_id=user_id,
                memory_ids=[hit.memory.memory_id for hit in selected],
            )
            # Caller is responsible for committing the session.
            # This avoids committing on a session the retriever doesn't own (W5/W7).
        return selected

    def _score(
        self,
        *,
        memory: AgentMemory,
        query: str,
        project_id: uuid.UUID | None,
        now: datetime,
    ) -> MemorySearchHit:
        breakdown = MemoryScoreBreakdown(
            text_match=self.text_match(query, self._searchable_text(memory)),
            importance=float(memory.importance),
            confidence=float(memory.confidence),
            recency=self.recency_score(memory.updated_at, now),
            access_weight=self.access_score(memory.access_count),
            project_relevance=self.project_score(
                memory.project_id,
                project_id,
            ),
        )
        weights = self.settings.normalized_memory_weights()
        score = sum(
            getattr(breakdown, name) * weight
            for name, weight in weights.items()
        )
        return MemorySearchHit(
            memory=MemoryRead.model_validate(memory),
            score=round(score, 6),
            score_breakdown=breakdown,
        )

    @staticmethod
    def text_match(query: str, content: str) -> float:
        query_tokens = set(TOKEN_PATTERN.findall(query.casefold()))
        content_tokens = set(TOKEN_PATTERN.findall(content.casefold()))
        if not query_tokens:
            return 1.0
        if not content_tokens:
            return 0.0
        return len(query_tokens & content_tokens) / len(query_tokens)

    @staticmethod
    def recency_score(updated_at: datetime, now: datetime) -> float:
        value = (
            updated_at.replace(tzinfo=UTC)
            if updated_at.tzinfo is None
            else updated_at.astimezone(UTC)
        )
        age_days = max((now - value).total_seconds() / 86400, 0)
        return math.exp(-age_days / 30)

    @staticmethod
    def access_score(access_count: int) -> float:
        return min(math.log1p(max(access_count, 0)) / math.log(11), 1.0)

    @staticmethod
    def project_score(
        memory_project_id: uuid.UUID | None,
        requested_project_id: uuid.UUID | None,
    ) -> float:
        if requested_project_id and memory_project_id == requested_project_id:
            return 1.0
        if memory_project_id is None:
            return 0.5
        return 0.0

    @staticmethod
    def _searchable_text(memory: AgentMemory) -> str:
        return " ".join(
            [
                memory.summary or "",
                memory.content,
                " ".join(memory.tags),
            ]
        )
