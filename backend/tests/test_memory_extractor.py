from uuid import uuid4

from app.memory.extractor import MockMemoryExtractor


def test_explicit_project_fact_becomes_project_memory() -> None:
    project_id = uuid4()
    run_id = uuid4()

    commands = MockMemoryExtractor().extract(
        text="Remember that Paris Agent uses Milvus in P7.",
        project_id=project_id,
        run_id=run_id,
    )

    assert len(commands) == 1
    assert commands[0].memory_type == "project"
    assert commands[0].scope == "project"
    assert commands[0].project_id == project_id
    assert commands[0].source_detail == {
        "rule": "explicit_remember",
        "run_id": str(run_id),
    }


def test_learning_preference_becomes_user_memory() -> None:
    commands = MockMemoryExtractor().extract(
        text="I prefer learning with small runnable examples.",
        project_id=None,
        run_id=uuid4(),
    )

    assert commands[0].memory_type == "learning_profile"
    assert commands[0].scope == "user"
    assert commands[0].project_id is None


def test_text_without_memory_signal_is_ignored() -> None:
    commands = MockMemoryExtractor().extract(
        text="Explain FastAPI dependency injection.",
        project_id=None,
        run_id=uuid4(),
    )

    assert commands == []
