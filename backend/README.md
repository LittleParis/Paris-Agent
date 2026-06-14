# Paris Agent Backend

## Setup

```powershell
Copy-Item .env.example .env
uv sync
```

On Windows, keep PostgreSQL configured with `127.0.0.1` instead of
`localhost` to avoid asyncpg IPv6 fallback delays.

## Database Migration

```powershell
uv run alembic upgrade head
uv run alembic current
```

Rollback the current migration:

```powershell
uv run alembic downgrade base
```

## Run

```powershell
uv run uvicorn app.main:app --reload
```

## Test

```powershell
uv run pytest
```

Available endpoints:

```text
GET  /health
POST /api/agent/runs
GET  /api/agent/runs/{run_id}
GET  /api/agent/runs/{run_id}/events
```

P1 uses an in-process mock runner and in-memory SSE event broker. RabbitMQ,
LangGraph, Skills, tools, memory, and RAG are intentionally not connected yet.
