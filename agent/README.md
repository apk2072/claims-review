# agent

Stateful LangGraph assistant agent backed by Amazon Bedrock (Claude). Deployed as a long-running ECS Fargate service (not a Lambda) because it needs persistent SSE connections and stateful conversation checkpoints — mirrors the "Databricks App vs. model-serving endpoint" reasoning from the reference architecture.

Uses a Postgres-backed checkpointer for per-conversation state and a pgvector-backed store for long-term per-user memory.

## Run locally

```bash
uv run --package agent uvicorn agent.main:app --reload
uv run --package agent pytest
```
