---
run: run-claims-review-003
work_item: synthetic-claims-fixtures
intent: claims-review-platform
generated: 2026-07-07T00:10:00.000Z
status: passed
---

# Test Report: Synthetic claims document fixtures

## Summary

| Check | Result |
|---|---|
| `uv run python pipeline/tests/fixtures/sample_claims/generate_fixtures.py` | ✅ generates all 4 PNGs |
| File sizes | ✅ 10-18 KB each, well under any LFS concern |
| Visual inspection (clean + blurry) | ✅ clean form is crisp/legible; blurred form is visibly degraded but still human-readable — appropriate for a "low confidence" OCR scenario |
| `uv run ruff check pipeline/` / `ruff format --check pipeline/` | ✅ clean |

## Acceptance Criteria Validation

- ✅ **4+ synthetic PDF/image fixtures saved under `pipeline/tests/fixtures/sample_claims/`** — 4 PNGs generated
- ✅ **Each fixture uses clearly fake identifiers** — `Jane Test Doe`, `TEST-000000`/`TEST-000001`, fabricated codes
- ✅ **`fixtures/README.md` documents what each fixture exercises** — written, maps each fixture to the pipeline behavior it's meant to trigger
- ✅ **Fixtures small enough to commit directly** — 10-18 KB each
- ✅ **Generation script kept** — `generate_fixtures.py`, re-runnable, more scenarios can be added later

## Tests Written

### Unit Tests

(none — this is fixture generation tooling, not application logic; correctness verified by running the script and inspecting output)

### Integration Tests

(none — these fixtures will be exercised as inputs in the `bronze-textract-parse` work item's integration tests)

## Test Commands

```bash
uv run python pipeline/tests/fixtures/sample_claims/generate_fixtures.py
uv run ruff check pipeline/
uv run ruff format --check pipeline/
```

## Coverage Details

Not applicable — no application code.

## Issues Found

No issues found during testing.

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (n/a)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item: aurora-schema-migrations

### Summary

All verification against the real dev Aurora cluster (via the RDS Data API — no VPC access from this machine). One real interoperability bug found and fixed along the way (pgvector bind-parameter casting).

| Check | Result |
|---|---|
| `alembic upgrade head` against real Aurora | ✅ (after `DatabaseResumingException` cold-start retry) — all 5 tables + `alembic_version` created |
| HNSW index on `agent_memory.embedding` | ✅ confirmed via `pg_indexes` |
| `common/tests/test_schema.py` (insert + read 1 row per table, real Aurora) | ❌ first run — pgvector bind-parameter type mismatch |
| Fix (`common.models.Vector` with explicit `::vector` cast) + re-run | ✅ passes |
| Post-test residue check (`SELECT count(*)` on `claims`/`agent_memory`) | ✅ 0 rows — rollback-based test fixture leaves no residue |
| `uv run ruff check .` / `ruff format --check .` (whole repo) | ✅ clean |

### Acceptance Criteria Validation

- ✅ **SQLAlchemy models defined in `common/`** — `common/src/common/models.py`: `Claim`, `Extraction`, `Review`, `ReviewMetric`, `AgentMemory`
- ✅ **Alembic migration creates all tables plus pgvector extension/index on `agent_memory.embedding`** — `CREATE EXTENSION IF NOT EXISTS vector` + HNSW cosine index, both confirmed live
- ✅ **`reviews` table captures reviewer identity, timestamp, verdict, links back to `extractions`** — `reviewer_email`, `created_at`, `verdict`, `extraction_id` FK
- ✅ **Migration runs cleanly against the Aurora cluster from work item 2 (`alembic upgrade head`)** — confirmed against the real deployed cluster
- ✅ **Integration test inserts and reads one row per table** — `common/tests/test_schema.py`, passing

### Tests Written

#### Unit Tests

(none — schema/migration code; correctness verified against the real cluster per `testing-standards.md`'s integration category)

#### Integration Tests

- `common/tests/test_schema.py::test_insert_and_read_one_row_per_table` — inserts + reads one row in all 5 tables against real Aurora, rolls back (no residue), skipped automatically if `AURORA_CLUSTER_ARN` isn't set

### Test Commands

```bash
export AURORA_CLUSTER_ARN=$(aws rds describe-db-clusters --region us-east-1 \
  --query "DBClusters[?contains(DBClusterIdentifier, 'auroracluster')].DBClusterArn" --output text)
export AURORA_SECRET_ARN=<from cdk outputs>
export AURORA_DATABASE_NAME=claims_review

uv run --package common alembic upgrade head
uv run --package common pytest common/tests/test_schema.py -v
uv run ruff check . && uv run ruff format --check .
```

### Coverage Details

Not applicable — schema/migration code, no coverage target per `testing-standards.md`.

### Issues Found

| Issue | Severity | Status |
|---|---|---|
| `alembic revision --autogenerate` fails against the Data API (`UnsupportedResultException` — Data API can't serialize the `CHAR` result type produced by `information_schema.columns` reflection) | low (workflow limitation, not a defect) | worked around — hand-wrote the initial migration (no reflection needed for a from-scratch schema); documented in `common/README.md` for future migrations |
| pgvector bind parameters sent via Data API skip Postgres type-OID negotiation, arrive as plain text, insert fails with `column "embedding" is of type vector but expression is of type text` | medium (would have blocked any real insert into `agent_memory`, not just the test) | fixed — `common.models.Vector` subclass adds an explicit `::vector` cast via `bind_expression`; safe/no-op for real `psycopg` connections too, so used everywhere, not just in the Data-API path |

### Ready for Completion

- [x] All tests passing
- [x] Coverage target met (n/a)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-003*
