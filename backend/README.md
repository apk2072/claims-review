# backend

FastAPI reviewer backend API — serves the review queue, claim detail, dashboard metrics, and the atomic verdict-submission endpoint.

## Run locally

```bash
uv run --package backend uvicorn backend.main:app --reload
uv run --package backend pytest
```

Requires `DATABASE_URL` pointing at the Aurora Postgres cluster (or a local Postgres instance for development).
