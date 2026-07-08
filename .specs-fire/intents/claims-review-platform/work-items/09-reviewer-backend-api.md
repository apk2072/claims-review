---
id: reviewer-backend-api
title: Reviewer backend API (FastAPI)
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [aurora-schema-migrations, gold-verdict-routing]
created: 2026-07-05T00:00:00Z
---

# Work Item: Reviewer backend API (FastAPI)

## Description

FastAPI service exposing: a review queue endpoint (documents pending human review, stratified by stage), a claim detail endpoint (extracted fields + confidence + document image/parse data), a verdict-submission endpoint implementing the atomic write pattern (status update + audit row insert + metrics increment, all in one DB transaction), and a dashboard/metrics summary endpoint.

## Acceptance Criteria

- [ ] `GET /claims/queue` returns claims grouped by processing stage (auto-verified vs. pending human review)
- [ ] `GET /claims/{id}` returns full extraction detail for one claim
- [ ] `POST /claims/{id}/verdict` performs the atomic write: updates `reviews.status`, inserts an audit row, increments the aggregate metrics — all in one transaction, verified with a test that a simulated mid-transaction failure leaves no partial state
- [ ] `GET /dashboard/summary` returns extraction accuracy / reviewer performance / pipeline efficiency aggregates
- [ ] OpenAPI docs available at `/docs`
- [ ] Integration tests against a real (or locally-run) Postgres instance cover the queue, detail, and verdict endpoints

## Technical Notes

The atomic verdict write is one of the most interview-relevant pieces of the whole project — it's worth being able to walk through the transaction boundary explicitly. Not deployed to ECS Fargate yet in this item if time is tight — running locally (`uvicorn`) against the Aurora dev cluster is enough to unblock the frontend; containerize/deploy to Fargate can be folded into this item or done as a quick follow-up if time allows.

## Dependencies

- aurora-schema-migrations
- gold-verdict-routing
