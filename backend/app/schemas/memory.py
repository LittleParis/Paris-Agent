"""Long-term memory request, response, and retrieval contracts."""

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

from app.memory.deduplicator import normalize_content, normalize_tags


MemoryType = Literal[
    "short_term",
    "learning_profile",
    "semantic",
    "episodic",
    "project",
    "procedural",
    "task",
    "runtime",
]
MemoryScope = Literal["user", "project"]
MemorySourceType = Literal["manual", "agent_run", "consolidation"]
MemorySyncStatus = Literal[
    "not_indexed",
    "pending",
    "syncing",
    "succeeded",
    "failed",
    "deleting",
    "deleted",
]
MemoryScore = Annotated[
    Decimal,
    Field(ge=0, le=1, max_digits=5, decimal_places=4),
]
SCORE_QUANTUM = Decimal("0.0001")


class StrictMemoryModel(BaseModel):
    """Base contract that rejects undeclared public fields."""

    model_config = ConfigDict(extra="forbid")


def _quantize_score(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("score must be a decimal number")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("score must be a decimal number") from None
    if not decimal_value.is_finite():
        raise ValueError("score must be finite")
    return decimal_value.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def _validate_normalized_tags(value: list[str]) -> list[str]:
    tags = normalize_tags(value)
    if len(tags) > 20:
        raise ValueError("tags must contain at most 20 values")
    if any(len(tag) > 64 for tag in tags):
        raise ValueError("each tag must contain at most 64 characters")
    return tags


class MemoryFields(StrictMemoryModel):
    """Fields shared by validated memory creation commands."""

    memory_type: MemoryType
    scope: MemoryScope
    project_id: uuid.UUID | None = None
    content: str
    summary: str | None = None
    importance: MemoryScore
    confidence: MemoryScore
    tags: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return _validate_normalized_tags(value)

    @field_validator("importance", "confidence", mode="before")
    @classmethod
    def quantize_score(cls, value: object) -> Decimal:
        return _quantize_score(value)

    @model_validator(mode="after")
    def validate_scope(self) -> "MemoryFields":
        if self.scope == "user" and self.project_id is not None:
            raise ValueError("project_id must be null for user scope")
        if self.scope == "project" and self.project_id is None:
            raise ValueError("project_id is required for project scope")
        if self.memory_type == "project" and self.scope != "project":
            raise ValueError("project memories must use project scope")
        return self

    @field_serializer("importance", "confidence", when_used="json")
    def serialize_decimal_score(self, value: Decimal) -> str:
        return f"{value:.4f}"


class MemoryCreate(MemoryFields):
    """Client request for a manually managed memory."""


class MemoryUpdate(StrictMemoryModel):
    """Optimistic partial update of client-mutable memory fields."""

    version: int = Field(ge=1)
    memory_type: MemoryType | None = None
    scope: MemoryScope | None = None
    project_id: uuid.UUID | None = None
    content: str | None = None
    summary: str | None = None
    importance: MemoryScore | None = None
    confidence: MemoryScore | None = None
    tags: list[str] | None = None
    expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("content must not be null")
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_content(value)
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str]:
        if value is None:
            raise ValueError("tags must not be null")
        return _validate_normalized_tags(value)

    @field_validator("importance", "confidence", mode="before")
    @classmethod
    def quantize_score(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return _quantize_score(value)

    @model_validator(mode="after")
    def validate_update(self) -> "MemoryUpdate":
        changed_fields = self.model_fields_set - {"version"}
        if not changed_fields:
            raise ValueError("at least one mutable field is required")

        for field_name in (
            "memory_type",
            "scope",
            "importance",
            "confidence",
        ):
            if field_name in changed_fields and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} must not be null")

        return self

    @field_serializer("importance", "confidence", when_used="json")
    def serialize_decimal_score(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.4f}"


class MemoryRead(StrictMemoryModel):
    """Public memory resource without ownership or projection internals."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    memory_id: uuid.UUID
    project_id: uuid.UUID | None
    memory_type: MemoryType
    scope: MemoryScope
    content: str
    summary: str | None
    importance: MemoryScore
    confidence: MemoryScore
    source_type: MemorySourceType
    source_id: uuid.UUID | None
    source_detail: dict[str, JsonValue]
    tags: list[str]
    version: int
    access_count: int
    last_accessed_at: datetime | None
    expires_at: datetime | None
    sync_status: MemorySyncStatus
    created_at: datetime
    updated_at: datetime

    @field_validator("importance", "confidence", mode="before")
    @classmethod
    def quantize_score(cls, value: object) -> Decimal:
        return _quantize_score(value)

    @field_serializer("importance", "confidence", when_used="json")
    def serialize_decimal_score(self, value: Decimal) -> str:
        return f"{value:.4f}"


class MemoryListResponse(StrictMemoryModel):
    """Cursor-paginated memory list."""

    items: list[MemoryRead]
    next_cursor: str | None


class MemorySearchRequest(StrictMemoryModel):
    """Deterministic memory search filters."""

    query: str = ""
    memory_types: list[MemoryType] = Field(default_factory=list)
    project_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return normalize_content(value)

    @field_validator("tags")
    @classmethod
    def normalize_search_tags(cls, value: list[str]) -> list[str]:
        return _validate_normalized_tags(value)


class MemoryScoreBreakdown(StrictMemoryModel):
    """Normalized components contributing to a retrieval score."""

    text_match: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    recency: float = Field(ge=0, le=1)
    access_weight: float = Field(ge=0, le=1)
    project_relevance: float = Field(ge=0, le=1)


class MemorySearchHit(StrictMemoryModel):
    """One scored memory result."""

    memory: MemoryRead
    score: float = Field(ge=0, le=1)
    score_breakdown: MemoryScoreBreakdown


class MemorySearchResponse(StrictMemoryModel):
    """Ordered memory search results."""

    items: list[MemorySearchHit]


class ConsolidationMemoryCommand(MemoryFields):
    """Validated deterministic extractor output."""

    source_detail: dict = Field(default_factory=dict)


class MemoryWriteResult(StrictMemoryModel):
    """Result of a controlled memory write or exact deduplication."""

    memory: MemoryRead
    created: bool
    deduplicated: bool
