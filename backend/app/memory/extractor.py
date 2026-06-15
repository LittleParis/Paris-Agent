from __future__ import annotations

import re
import uuid
from decimal import Decimal

from app.schemas.memory import ConsolidationMemoryCommand

WHITESPACE = re.compile(r"\s+")
EXPLICIT_PATTERNS = (
    re.compile(r"^\s*remember(?:\s+that)?\s+(.+)$", re.IGNORECASE),
    re.compile(r"^\s*请记住[：:\s]*(.+)$"),
    re.compile(r"^\s*记住[：:\s]*(.+)$"),
)
LEARNING_PATTERNS = (
    re.compile(r"\bi prefer learning\b", re.IGNORECASE),
    re.compile(r"\bmy learning preference\b", re.IGNORECASE),
    re.compile(r"我(?:更)?喜欢(?:通过|用).+学习"),
    re.compile(r"我的学习偏好"),
)


class MockMemoryExtractor:
    def extract(
        self,
        *,
        text: str,
        project_id: uuid.UUID | None,
        run_id: uuid.UUID,
    ) -> list[ConsolidationMemoryCommand]:
        normalized = WHITESPACE.sub(" ", text).strip()
        if not normalized:
            return []

        explicit = self._explicit_content(normalized)
        learning = any(pattern.search(normalized) for pattern in LEARNING_PATTERNS)
        if explicit is None and not learning:
            return []

        content = explicit or normalized
        memory_type = (
            "learning_profile"
            if learning
            else "project"
            if project_id is not None
            else "semantic"
        )
        scope = "project" if project_id is not None else "user"
        tags = [memory_type]
        if project_id is not None:
            tags.append(str(project_id))

        return [
            ConsolidationMemoryCommand(
                memory_type=memory_type,
                scope=scope,
                project_id=project_id,
                content=content,
                summary=content[:240],
                importance=Decimal("0.7000"),
                confidence=Decimal("0.8500"),
                tags=tags,
                source_detail={
                    "rule": (
                        "learning_preference"
                        if learning
                        else "explicit_remember"
                    ),
                    "run_id": str(run_id),
                },
            )
        ]

    @staticmethod
    def _explicit_content(text: str) -> str | None:
        for pattern in EXPLICIT_PATTERNS:
            match = pattern.match(text)
            if match:
                return match.group(1).strip().rstrip(".。")
        return None
