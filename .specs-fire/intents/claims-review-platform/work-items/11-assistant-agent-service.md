---
id: assistant-agent-service
title: Assistant agent service (LangGraph + Bedrock)
intent: claims-review-platform
complexity: high
mode: validate
status: pending
depends_on: [aurora-schema-migrations, reviewer-backend-api]
created: 2026-07-05T00:00:00Z
---

# Work Item: Assistant agent service (LangGraph + Bedrock)

## Description

Stateful LangGraph agent, backed by Bedrock (Claude), exposed via an SSE streaming endpoint for the reviewer app's chat panel. Uses a Postgres-backed checkpointer for per-conversation state and a pgvector-backed store for long-term per-user memory, with row-level isolation so one reviewer's conversation/memory isn't visible to another. Given the SSE/stateful requirement, deployed as a long-running ECS Fargate service rather than a request/response-only Lambda.

## Acceptance Criteria

- [ ] Agent answers natural-language questions over Aurora review data via tool calls (e.g. "how many claims did I review today", "show me the lowest-confidence extraction from yesterday")
- [ ] Conversation state persists across turns using a Postgres checkpointer (`agent_memory`/checkpoint tables from work item 3)
- [ ] Long-term memory stores and retrieves via pgvector similarity search, scoped per user
- [ ] Row-level isolation verified with a test: user A's tool calls cannot return user B's data
- [ ] SSE endpoint streams tokens to the frontend chat panel from work item 10, replacing the placeholder
- [ ] Deployed as an ECS Fargate service (Dockerfile + CDK service definition), not Lambda

## Technical Notes

Highest architectural complexity in the project — hence `validate` mode with a design doc first. Design doc should explicitly address: LangGraph state machine shape (which tools, which nodes), how row-level security is enforced (DB-level RLS vs. application-level scoping vs. both), and why this needs to be a long-lived Fargate service rather than a Lambda (mirrors the reference architecture's "Databricks App vs. model-serving endpoint" reasoning).

## Dependencies

- aurora-schema-migrations
- reviewer-backend-api
