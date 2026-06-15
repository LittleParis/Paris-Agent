import hashlib
from uuid import UUID

from app.memory.deduplicator import (
    compute_content_hash,
    normalize_content,
    normalize_tags,
)


def test_normalize_content_uses_nfkc_trim_and_whitespace_collapse() -> None:
    assert normalize_content("  ＰｏｓｔｇｒｅＳＱＬ\n\t索引  ") == "PostgreSQL 索引"


def test_normalize_content_preserves_case_and_punctuation() -> None:
    assert normalize_content(r"Path C:\Temp\A.py!") == r"Path C:\Temp\A.py!"


def test_normalize_tags_uses_nfkc_trim_deduplication_and_stable_sorting() -> None:
    assert normalize_tags(
        [" postgres ", "Ｉｎｄｅｘ", "", "postgres", "  ", "索引"]
    ) == ["Index", "postgres", "索引"]


def test_normalize_tags_preserves_case_and_collapses_internal_whitespace() -> None:
    assert normalize_tags([" Tag ", "tag", "two  words"]) == [
        "Tag",
        "tag",
        "two words",
    ]


def test_content_hash_uses_only_identity_fields_and_normalized_content() -> None:
    expected_input = "semantic\nuser\n\nPostgreSQL Index"
    expected = hashlib.sha256(expected_input.encode("utf-8")).hexdigest()

    actual = compute_content_hash(
        memory_type="semantic",
        scope="user",
        project_id=None,
        content="  ＰｏｓｔｇｒｅＳＱＬ \n Index ",
    )

    assert actual == expected
    assert len(actual) == 64


def test_content_hash_changes_with_type_scope_project_or_content_case() -> None:
    project_id = UUID("11111111-1111-1111-1111-111111111111")
    base = compute_content_hash(
        memory_type="semantic",
        scope="user",
        project_id=None,
        content="PostgreSQL index",
    )

    variants = {
        compute_content_hash(
            memory_type="learning_profile",
            scope="user",
            project_id=None,
            content="PostgreSQL index",
        ),
        compute_content_hash(
            memory_type="semantic",
            scope="project",
            project_id=project_id,
            content="PostgreSQL index",
        ),
        compute_content_hash(
            memory_type="semantic",
            scope="user",
            project_id=None,
            content="postgresql index",
        ),
    }

    assert base not in variants
    assert len(variants) == 3


def test_equivalent_unicode_and_whitespace_produce_same_hash() -> None:
    compact = compute_content_hash(
        memory_type="semantic",
        scope="user",
        project_id=None,
        content="PostgreSQL Index",
    )
    normalized = compute_content_hash(
        memory_type="semantic",
        scope="user",
        project_id=None,
        content="  ＰｏｓｔｇｒｅＳＱＬ\tIndex\n",
    )

    assert compact == normalized
