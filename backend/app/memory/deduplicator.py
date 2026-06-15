"""Deterministic normalization and exact memory deduplication."""

import hashlib
import unicodedata
from collections.abc import Iterable
from uuid import UUID


def normalize_content(value: str) -> str:
    """Normalize Unicode and whitespace without changing case or punctuation."""

    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().split())


def normalize_tags(tags: Iterable[str]) -> list[str]:
    """Normalize, remove empty values, deduplicate, and sort tags."""

    normalized_tags: set[str] = set()
    for tag in tags:
        normalized = normalize_content(tag)
        if normalized:
            normalized_tags.add(normalized)
    return sorted(normalized_tags)


def compute_content_hash(
    *,
    memory_type: str,
    scope: str,
    project_id: UUID | None,
    content: str,
) -> str:
    """Hash the exact identity of an active memory."""

    canonical = "\n".join(
        (
            memory_type,
            scope,
            str(project_id) if project_id is not None else "",
            normalize_content(content),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
