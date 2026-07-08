---
id: aurora-schema-migrations
title: Aurora schema and migrations
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [aws-foundation-infra]
created: 2026-07-05T00:00:00Z
---

# Work Item: Aurora schema and migrations

## Description

SQLAlchemy models + Alembic migrations for the operational schema: `claims` (document metadata), `extractions` (gold-layer field/value + confidence data), `reviews` (verdict + audit trail), `review_metrics` (materialized/aggregated supervisor metrics), and `agent_memory` (pgvector-backed long-term agent memory, per-user).

## Acceptance Criteria

- [ ] SQLAlchemy models defined in a shared `common/` package importable by pipeline, backend, and agent
- [ ] Alembic migration creates all tables plus the pgvector extension/index on `agent_memory.embedding`
- [ ] `reviews` table captures reviewer identity, timestamp, verdict (approved/rejected/corrected), and links back to the `extractions` row it verdicts
- [ ] Migration runs cleanly against the Aurora cluster from work item 2 (`alembic upgrade head`)
- [ ] Basic integration test (pytest + real dev Aurora, or moto/local Postgres) inserts and reads one row per table

## Technical Notes

Schema should support the "verdict atomicity" pattern from the reference architecture: a single reviewer verdict needs to update `reviews.status`, insert an audit row, and be aggregatable into `review_metrics` — design the schema so those three things can happen in one transaction from the backend, even though the actual atomic-write logic is implemented in work item 9.

## Dependencies

- aws-foundation-infra
