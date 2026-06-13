# Paris Agent Frontend

Vue 3, TypeScript, and Vite frontend for the Paris Agent Workbench.

## Setup

```powershell
Copy-Item .env.example .env
pnpm install
```

## Run

```powershell
pnpm dev
```

## Build

```powershell
pnpm build
```

The P0 frontend exposes `/dashboard` and initializes Vue Router, Pinia, Axios,
Element Plus, TanStack Query for Vue, ECharts, and Monaco Editor.
