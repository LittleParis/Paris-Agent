# Paris Agent Backend

## Setup

```powershell
Copy-Item .env.example .env
uv sync
```

## Run

```powershell
uv run uvicorn app.main:app --reload
```

## Test

```powershell
uv run pytest
```

The P0 API exposes `GET /health`. Database models and Alembic migrations will
be added in the phase that introduces persistent domain data.
