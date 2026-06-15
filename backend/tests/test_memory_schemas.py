from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.memory import (
    ConsolidationMemoryCommand,
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemoryScoreBreakdown,
    MemorySearchHit,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryUpdate,
    MemoryWriteResult,
)


def build_create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "memory_type": "learning_profile",
        "scope": "user",
        "project_id": None,
        "content": "  Learning\n PostgreSQL  ",
        "summary": None,
        "importance": Decimal("0.8"),
        "confidence": Decimal("0.9"),
        "tags": [" postgres ", "index", "postgres"],
        "expires_at": None,
    }
    payload.update(overrides)
    return payload


def build_read(**overrides: object) -> MemoryRead:
    timestamp = datetime(2026, 6, 15, tzinfo=UTC)
    payload: dict[str, object] = {
        "memory_id": UUID("11111111-1111-1111-1111-111111111111"),
        "project_id": None,
        "memory_type": "learning_profile",
        "scope": "user",
        "content": "Learning PostgreSQL",
        "summary": None,
        "importance": Decimal("0.8"),
        "confidence": Decimal("0.98765"),
        "source_type": "manual",
        "source_id": None,
        "source_detail": {"created_via": "memory_api"},
        "tags": ["index", "postgres"],
        "version": 1,
        "access_count": 0,
        "last_accessed_at": None,
        "expires_at": None,
        "sync_status": "not_indexed",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    payload.update(overrides)
    return MemoryRead.model_validate(payload)


def test_memory_create_normalizes_mutable_text_and_tags() -> None:
    payload = MemoryCreate.model_validate(build_create_payload())

    assert payload.content == "Learning PostgreSQL"
    assert payload.tags == ["index", "postgres"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (Decimal("0"), Decimal("0.0000")),
        (Decimal("1"), Decimal("1.0000")),
        (Decimal("0.12344"), Decimal("0.1234")),
        (Decimal("0.12345"), Decimal("0.1235")),
        (Decimal("0.99995"), Decimal("1.0000")),
        (Decimal("1.00004"), Decimal("1.0000")),
        (Decimal("-0.00004"), Decimal("-0.0000")),
    ],
)
def test_memory_create_quantizes_scores_like_postgresql_numeric(
    raw: Decimal,
    expected: Decimal,
) -> None:
    payload = MemoryCreate.model_validate(
        build_create_payload(importance=raw, confidence=raw)
    )

    assert payload.importance == expected
    assert payload.confidence == expected
    assert isinstance(payload.importance, Decimal)


@pytest.mark.parametrize(
    "raw",
    [
        Decimal("-0.00005"),
        Decimal("1.00005"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_memory_create_rejects_scores_outside_numeric_boundaries(
    raw: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(
            build_create_payload(importance=raw, confidence=raw)
        )


def test_create_update_and_command_share_score_quantization() -> None:
    create = MemoryCreate.model_validate(
        build_create_payload(importance="0.55555", confidence="0.44444")
    )
    update = MemoryUpdate(
        version=1,
        importance="0.55555",
        confidence="0.44444",
    )
    command = ConsolidationMemoryCommand.model_validate(
        {
            **build_create_payload(
                importance="0.55555",
                confidence="0.44444",
            ),
            "source_detail": {},
        }
    )

    for model in (create, update, command):
        assert model.importance == Decimal("0.5556")
        assert model.confidence == Decimal("0.4444")


def test_write_schema_decimal_serializer_only_changes_json_dump() -> None:
    models = (
        MemoryCreate.model_validate(build_create_payload()),
        MemoryUpdate(
            version=1,
            importance=Decimal("0.8"),
            confidence=Decimal("0.9"),
        ),
        ConsolidationMemoryCommand.model_validate(
            {**build_create_payload(), "source_detail": {}}
        ),
    )

    for model in models:
        python_payload = model.model_dump()
        json_payload = model.model_dump(mode="json")
        assert python_payload["importance"] == Decimal("0.8000")
        assert python_payload["confidence"] == Decimal("0.9000")
        assert isinstance(python_payload["importance"], Decimal)
        assert json_payload["importance"] == "0.8000"
        assert json_payload["confidence"] == "0.9000"


def test_write_schema_datetime_uses_json_iso_string() -> None:
    expires_at = datetime(2026, 7, 1, 12, 30, tzinfo=UTC)
    create = MemoryCreate.model_validate(
        build_create_payload(expires_at=expires_at)
    )

    assert create.model_dump()["expires_at"] == expires_at
    assert (
        create.model_dump(mode="json")["expires_at"]
        == "2026-07-01T12:30:00Z"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"scope": "project", "project_id": None},
        {"scope": "user", "project_id": uuid4()},
        {"memory_type": "project", "scope": "user", "project_id": None},
    ],
)
def test_memory_create_rejects_invalid_scope_project_type_combinations(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(build_create_payload(**payload))


def test_memory_create_accepts_project_memory_with_project_scope() -> None:
    project_id = uuid4()

    payload = MemoryCreate.model_validate(
        build_create_payload(
            memory_type="project",
            scope="project",
            project_id=project_id,
        )
    )

    assert payload.project_id == project_id


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "source_type",
        "source_id",
        "source_detail",
        "content_hash",
        "external_vector_id",
        "embedding_version",
        "sync_status",
        "last_synced_at",
        "sync_error",
    ],
)
def test_memory_create_rejects_client_owned_or_internal_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(
            build_create_payload(**{field: "forged"})
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"content": " \n\t "},
        {"summary": " \n\t "},
        {"importance": Decimal("-0.0001")},
        {"confidence": Decimal("1.0001")},
        {"tags": [f"tag-{index}" for index in range(21)]},
        {"tags": ["x" * 65]},
    ],
)
def test_memory_create_rejects_invalid_content_scores_and_tags(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(build_create_payload(**payload))


def test_memory_update_requires_version_and_a_mutation() -> None:
    with pytest.raises(ValidationError):
        MemoryUpdate()
    with pytest.raises(ValidationError):
        MemoryUpdate(version=1)


def test_memory_update_normalizes_values_and_allows_nullable_mutations() -> None:
    update = MemoryUpdate(
        version=3,
        content="  Updated\n content ",
        tags=[" beta ", "alpha", "alpha"],
        summary=None,
        expires_at=None,
    )

    assert update.content == "Updated content"
    assert update.tags == ["alpha", "beta"]
    assert {"summary", "expires_at"} <= update.model_fields_set


@pytest.mark.parametrize(
    "field",
    ["memory_type", "scope", "content", "importance", "confidence", "tags"],
)
def test_memory_update_rejects_null_for_non_nullable_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate({"version": 1, field: None})


@pytest.mark.parametrize(
    "payload",
    [
        {"scope": "user"},
        {"scope": "project"},
        {"project_id": uuid4()},
        {"project_id": None},
        {"memory_type": "project"},
    ],
)
def test_memory_update_accepts_partial_scope_type_mutations(
    payload: dict[str, object],
) -> None:
    update = MemoryUpdate.model_validate({"version": 1, **payload})

    assert update.model_fields_set == {"version", *payload}


def test_memory_update_allows_clearing_project_id_when_switching_to_user() -> None:
    update = MemoryUpdate(version=1, scope="user", project_id=None)

    assert update.scope == "user"
    assert update.project_id is None


def test_memory_update_rejects_source_and_projection_fields() -> None:
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate(
            {"version": 1, "source_type": "manual"}
        )
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate(
            {"version": 1, "external_vector_id": "vector-1"}
        )


def test_consolidation_command_is_the_only_write_schema_with_source_detail() -> None:
    command = ConsolidationMemoryCommand.model_validate(
        {
            **build_create_payload(),
            "source_detail": {"rule": "explicit_remember"},
        }
    )

    assert command.source_detail == {"rule": "explicit_remember"}


def test_consolidation_command_still_rejects_source_identity_fields() -> None:
    with pytest.raises(ValidationError):
        ConsolidationMemoryCommand.model_validate(
            {
                **build_create_payload(),
                "source_type": "consolidation",
                "source_id": str(uuid4()),
            }
        )


@pytest.mark.parametrize(
    "source_detail",
    [
        {"rule": "explicit_remember"},
        {"nested": [{"key": "value"}]},
        {"extractor": "deterministic_v1", "attempt": 1, "active": True},
    ],
)
def test_source_detail_accepts_arbitrary_dict_values(
    source_detail: dict[str, object],
) -> None:
    command = ConsolidationMemoryCommand.model_validate(
        {
            **build_create_payload(),
            "source_detail": source_detail,
        }
    )
    assert command.source_detail == source_detail
    read = build_read(source_detail=source_detail)
    assert read.source_detail == source_detail


def test_json_source_detail_accepts_recursive_json_values() -> None:
    source_detail = {
        "extractor": "deterministic_v1",
        "attempt": 1,
        "active": True,
        "optional": None,
        "nested": [{"score": 0.9}],
    }

    command = ConsolidationMemoryCommand.model_validate(
        {
            **build_create_payload(),
            "source_detail": source_detail,
        }
    )

    assert command.source_detail == source_detail


def test_decimal_serializer_only_changes_json_dump() -> None:
    memory = build_read()
    python_payload = memory.model_dump()
    json_payload = memory.model_dump(mode="json")

    assert python_payload["importance"] == Decimal("0.8000")
    assert python_payload["confidence"] == Decimal("0.9877")
    assert isinstance(python_payload["importance"], Decimal)
    assert json_payload["importance"] == "0.8000"
    assert json_payload["confidence"] == "0.9877"


def test_datetime_serializer_uses_json_iso_strings_only() -> None:
    memory = build_read()
    python_payload = memory.model_dump()
    json_payload = memory.model_dump(mode="json")

    assert python_payload["created_at"] == datetime(2026, 6, 15, tzinfo=UTC)
    assert isinstance(python_payload["created_at"], datetime)
    assert json_payload["created_at"] == "2026-06-15T00:00:00Z"
    assert json_payload["updated_at"] == "2026-06-15T00:00:00Z"


def test_memory_read_exposes_only_public_fields() -> None:
    payload = build_read().model_dump()

    assert set(payload) == {
        "memory_id",
        "project_id",
        "memory_type",
        "scope",
        "content",
        "summary",
        "importance",
        "confidence",
        "source_type",
        "source_id",
        "source_detail",
        "tags",
        "version",
        "access_count",
        "last_accessed_at",
        "expires_at",
        "sync_status",
        "created_at",
        "updated_at",
    }


def test_memory_read_supports_from_attributes() -> None:
    source = SimpleNamespace(**build_read().model_dump())

    memory = MemoryRead.model_validate(source)

    assert memory.memory_id == source.memory_id
    assert memory.importance == Decimal("0.8000")


def test_list_search_and_write_result_contracts() -> None:
    memory = build_read()
    breakdown = MemoryScoreBreakdown(
        text_match=0.75,
        importance=0.8,
        confidence=0.9,
        recency=0.7,
        access_weight=0.2,
        project_relevance=0.5,
    )
    hit = MemorySearchHit(
        memory=memory,
        score=0.82,
        score_breakdown=breakdown,
    )

    assert MemoryListResponse(items=[memory], next_cursor=None).items == [memory]
    assert MemorySearchResponse(items=[hit]).items == [hit]
    assert MemoryWriteResult(
        memory=memory,
        created=True,
        deduplicated=False,
    ).created


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            MemoryCreate,
            {**build_create_payload(), "unexpected": True},
        ),
        (
            MemoryUpdate,
            {"version": 1, "summary": None, "unexpected": True},
        ),
        (
            ConsolidationMemoryCommand,
            {
                **build_create_payload(),
                "source_detail": {},
                "unexpected": True,
            },
        ),
        (
            MemoryRead,
            {
                **build_read().model_dump(),
                "unexpected": True,
            },
        ),
        (
            MemoryListResponse,
            {"items": [], "next_cursor": None, "unexpected": True},
        ),
        (
            MemorySearchRequest,
            {"unexpected": True},
        ),
        (
            MemoryScoreBreakdown,
            {
                "text_match": 0.5,
                "importance": 0.5,
                "confidence": 0.5,
                "recency": 0.5,
                "access_weight": 0.5,
                "project_relevance": 0.5,
                "unexpected": True,
            },
        ),
        (
            MemorySearchHit,
            {
                "memory": build_read(),
                "score": 0.5,
                "score_breakdown": {
                    "text_match": 0.5,
                    "importance": 0.5,
                    "confidence": 0.5,
                    "recency": 0.5,
                    "access_weight": 0.5,
                    "project_relevance": 0.5,
                },
                "unexpected": True,
            },
        ),
        (
            MemorySearchResponse,
            {"items": [], "unexpected": True},
        ),
        (
            MemoryWriteResult,
            {
                "memory": build_read(),
                "created": True,
                "deduplicated": False,
                "unexpected": True,
            },
        ),
    ],
)
def test_public_response_and_search_schemas_forbid_extra_fields(
    schema: type,
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_memory_search_request_normalizes_query_and_tags() -> None:
    request = MemorySearchRequest(
        query="  ＰｏｓｔｇｒｅＳＱＬ\n index ",
        memory_types=["semantic"],
        tags=[" db ", "db", "Ｉｎｄｅｘ"],
        limit=10,
    )

    assert request.query == "PostgreSQL index"
    assert request.tags == ["Index", "db"]


def test_memory_search_request_rejects_invalid_limits_and_tags() -> None:
    with pytest.raises(ValidationError):
        MemorySearchRequest(limit=0)
    with pytest.raises(ValidationError):
        MemorySearchRequest(tags=["x" * 65])
    with pytest.raises(ValidationError):
        MemorySearchRequest(
            tags=[f"tag-{index}" for index in range(21)]
        )
