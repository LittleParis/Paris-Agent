# Paris Agent

Paris Agent is a Skill-based Agent Workbench for programmer learning,
knowledge retrieval, long-term memory, DAG ReAct execution, safe tool use, and
observable agent runs.

This repository currently implements the P0 project skeleton:

- FastAPI backend with `GET /health`
- Vue 3, TypeScript, and Vite dashboard shell
- Docker Compose services for PostgreSQL, Redis, and RabbitMQ
- Environment-driven configuration with committed `.env.example` files

## Prerequisites

- Python 3.11+
- uv
- Node.js 20+
- pnpm 10
- Docker Desktop with Docker Compose

## Start Infrastructure

```powershell
Set-Location docker
Copy-Item .env.example .env
docker compose up -d
docker compose ps
```

RabbitMQ management UI: `http://localhost:15672`

## Start Backend

```powershell
Set-Location backend
Copy-Item .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

Health endpoint: `http://localhost:8000/health`

## Start Frontend

```powershell
Set-Location frontend
Copy-Item .env.example .env
pnpm install
pnpm dev
```

Dashboard: `http://localhost:5173/dashboard`

If pnpm is available only through Corepack, replace `pnpm` with
`corepack pnpm`.

## Verify

```powershell
Set-Location backend
uv run pytest

Set-Location ..\frontend
pnpm build

Set-Location ..\docker
docker compose --env-file .env.example config
```

See [docs/FULLSTACK_TECH_DESIGN.md](docs/FULLSTACK_TECH_DESIGN.md) for the
phased architecture and implementation roadmap.
