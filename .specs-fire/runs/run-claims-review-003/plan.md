---
run: run-claims-review-003
work_item: synthetic-claims-fixtures
intent: claims-review-platform
mode: autopilot
checkpoint: none
approved_at: n/a (autopilot)
---

# Implementation Plan: Synthetic claims document fixtures

## Approach

Generate 4 synthetic claim document images with Pillow (already available in the workspace as a transitive dependency; adding it explicitly as a dev dependency since fixture generation is a real, repeatable tool, not incidental): a clean high-confidence claim form, the same form gaussian-blurred to simulate a low-quality scan, a form with required fields left blank, and a document that isn't a claim form at all (to exercise `ai_classify` later). All identifiers are obviously fake. Saved as PNG (Textract accepts PNG/JPEG directly, no PDF library needed). Generation script kept alongside the fixtures so more scenarios can be added later.

## Files to Create

| File | Purpose |
|------|---------|
| `pipeline/tests/fixtures/sample_claims/generate_fixtures.py` | Script that generates all 4 fixture images |
| `pipeline/tests/fixtures/sample_claims/clean_high_confidence.png` | Clean, fully-filled claim form |
| `pipeline/tests/fixtures/sample_claims/blurry_low_confidence.png` | Same content, gaussian-blurred |
| `pipeline/tests/fixtures/sample_claims/missing_fields.png` | Claim form missing required fields |
| `pipeline/tests/fixtures/sample_claims/wrong_document_type.png` | Non-claim document (grocery receipt) |
| `pipeline/tests/fixtures/sample_claims/README.md` | Documents what each fixture exercises |

## Files to Modify

| File | Changes |
|------|---------|
| `pyproject.toml` (root) | Add `pillow` to the dev dependency group |

## Tests

| Test File | Coverage |
|-----------|----------|
| (manual) | Run the generation script, confirm 4 PNGs produced, visually inspect via the file sizes/dimensions |

## Technical Details

Text rendered with Pillow's default bitmap font (no external font file dependency — keeps this fully offline/reproducible). Fake identifiers use an obviously-fake pattern (e.g. member ID `TEST-000000`, name "Jane Test Doe") per `testing-standards.md`'s test-data guidelines.

---

## Work Item: aurora-schema-migrations

### Approach

SQLAlchemy declarative models in `common/src/common/models.py` for `claims`, `extractions`, `reviews`, `review_metrics`, and `agent_memory` (pgvector column via the `pgvector` package's `Vector` type). Alembic lives under `common/` (config + `migrations/` directory) since the models live there too.

**Key decision — how Alembic reaches Aurora**: the cluster has no public endpoint (isolated subnet only, by design from work item 2), so a direct `psycopg` connection from this machine can't reach it. Rather than standing up a bastion/VPN, I smoke-tested the `aurora-data-api` package (a DBAPI/SQLAlchemy dialect built on the RDS Data API we already enabled on the cluster) — confirmed working against the real cluster (`SELECT 1` succeeded after one cold-start retry). Alembic's `sqlalchemy.url` will point at `postgresql+auroradataapi://` so migrations run over the Data API, no VPC network path needed. This is consistent with how pgvector was verified in work item 2.

Schema notes:
- `reviews` is insert-only — each row *is* an audit-trail entry (reviewer identity + timestamp + verdict), satisfying the "verdict atomicity" requirement's audit-trail half
- `review_metrics` is a per-reviewer-per-day aggregate row, incremented alongside each `reviews` insert (actual atomic-write logic lands in work item 9, `reviewer-backend-api`) — schema just needs to support that transaction shape
- `agent_memory.embedding` uses `Vector(1024)` (matches Amazon Titan Embed Text v2's default output dimension — configurable if a different Bedrock embedding model is chosen later in the agent work item)

### Files to Create

| File | Purpose |
|------|---------|
| `common/src/common/models.py` | SQLAlchemy declarative models: Claim, Extraction, Review, ReviewMetric, AgentMemory |
| `common/src/common/db.py` | Engine/session factory helpers (reads `DATABASE_URL` env var) |
| `common/alembic.ini` | Alembic config |
| `common/migrations/env.py` | Alembic environment, wired to the models' metadata |
| `common/migrations/script.py.mako` | Alembic's migration file template (standard) |
| `common/migrations/versions/0001_initial_schema.py` | Initial migration: all 5 tables + pgvector extension + HNSW index on `agent_memory.embedding` |
| `common/tests/test_schema.py` | Integration test: insert + read one row per table against the real Aurora cluster (via Data API) |
| `common/README.md` | How to run migrations, env vars needed |

### Files to Modify

| File | Changes |
|------|---------|
| `common/pyproject.toml` | Add `sqlalchemy`, `alembic`, `pgvector`, `psycopg[binary]`, `aurora-data-api` (already added while smoke-testing) |

### Tests

| Test File | Coverage |
|-----------|----------|
| `common/tests/test_schema.py` | Insert + read one row in each of the 5 tables against the real Aurora cluster |

### Technical Details

`alembic upgrade head` will be run directly against the deployed cluster from work item 2 using `DATABASE_URL=postgresql+auroradataapi://:@/claims_review?aurora_cluster_arn=<arn>&secret_arn=<arn>&region_name=us-east-1`, values sourced from the CDK stack outputs already captured in `/tmp/cdk-outputs.json`. `psycopg` stays a declared dependency for the components that *do* run inside the VPC later (backend, agent, pipeline Lambdas) — Alembic itself is the one exception using the Data API dialect for this local/no-VPC-access migration workflow.

---
*Autopilot mode for item 1 (no checkpoint) — plan for item 2 (aurora-schema-migrations, confirm mode) awaiting approval below.*

---
Approve this plan for `aurora-schema-migrations`? **[Y/n/edit]**
