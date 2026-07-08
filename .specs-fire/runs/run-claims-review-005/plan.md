---
run: run-claims-review-005
work_item: bronze-textract-parse
intent: claims-review-platform
mode: confirm
checkpoint: plan
approved_at:
---

# Implementation Plan: Bronze layer — Textract document parsing

## Approach

Replace the bronze placeholder Lambda (from `pipeline-orchestration`) with a real implementation that calls Amazon Textract `AnalyzeDocument` (FORMS) on the incoming S3 object, persists the parse result to Aurora, and hands off to the next state.

**Two decisions that shape this plan:**

1. **New `bronze_parses` table** (vs. reusing `claims`/`extractions`). Textract's raw per-element blocks (bounding boxes + confidences) are a distinct artifact from `claims` (lean identity row) and `extractions` (later structured field/verdict result from silver/gold). A dedicated table keeps both of those clean. Added via a hand-written Alembic migration (autogenerate still doesn't work over the Data API — same limitation documented in `common/README.md`).

2. **Lambda talks to Aurora via raw boto3 `rds-data` calls, not the `common` package's SQLAlchemy models.** `pipeline/pyproject.toml` already depends on `common`, which pulls in `psycopg[binary]` (a compiled dependency) — but this machine still has no Docker for Lambda asset bundling (the same constraint noted in `infra/README.md` for `ConnectivityTestFunction`). So the bronze Lambda uses parameterized SQL through the `rds-data` boto3 client directly (zero new dependencies, deployed via the existing `Code.from_inline` pattern, no VPC attachment needed — Data API works from outside the VPC, same mechanism Alembic already uses). This is a deliberate, documented deviation from `common/db.py`'s docstring (which describes pipeline as a `psycopg`-over-VPC caller) — revisit if/when this project adopts Docker-based Lambda bundling.

**Testing approach**: confirmed `moto` (5.2.2) does not implement `textract.analyze_document` (`NotImplementedError`) and its `rds-data` mock always returns empty `records` regardless of input — neither is useful for meaningful assertions. Per `testing-standards.md`'s explicit guidance ("Bedrock/Textract responses are captured once as fixture JSON from a real dev-account call, then replayed in tests"), I'll capture two real `AnalyzeDocument` responses (clean + blurry fixtures) via the AWS MCP server and replay them via `unittest.mock.patch` on the boto3 clients; `rds-data` responses are hand-crafted mock returns (simulating `RETURNING id`).

**Handler flow** (`pipeline/src/pipeline/bronze/parse_handler.py`):
1. Extract `bucket`/`key` from the EventBridge S3 event
2. Upsert `claims` row by `s3_key` (`INSERT ... ON CONFLICT (s3_key) DO UPDATE ... RETURNING id`) → `claim_id`
3. Call Textract `AnalyzeDocument(S3Object={bucket,key}, FeatureTypes=[FORMS])` via a boto3 client configured with adaptive retries (`Config(retries={"max_attempts": 5, "mode": "adaptive"})`) for transient errors
4. On permanent failure (retries exhausted): update `claims.status = 'failed'`, then re-raise — the existing Step Functions `.add_catch()` from `pipeline-orchestration` already routes this to the shared `DocumentProcessingFailed` Fail state, so no state-machine change needed
5. On success: trim `Blocks` to `{BlockType, Text, Confidence, Geometry.BoundingBox}`, compute `parse_confidence` = mean confidence of `WORD` blocks ÷ 100 (0.0 if none)
6. Upsert `bronze_parses` row (`claim_id` unique) with the trimmed blocks + `parse_confidence`
7. Return `{"claim_id", "bucket", "key", "parse_confidence"}` — replaces the current raw-event passthrough, and is the shape `silver-classify-extract` will consume next

**Real-AWS action disclosure**: approving this plan authorizes:
- Running the new Alembic migration against the real deployed Aurora cluster (same Data API mechanism as `aurora-schema-migrations`)
- A handful of real Textract `AnalyzeDocument` calls (~2 for fixture capture + up to 4 for manual verification) — AnalyzeDocument FORMS is ~$0.05/page; single-page test images, total cost a few cents
- `cdk deploy` of the updated `ClaimsReviewPipelineStack` (new IAM grants on the existing `BronzeParseFunction`, no new resources)
- All AWS calls (migration execution, Textract fixture capture, manual verification, DB queries) go through the AWS MCP server (`call_aws`), not local CLI/boto3, per your instruction. `cdk deploy`/`alembic upgrade` remain local build/deploy-tool invocations.

## Files to Create

| File | Purpose |
|------|---------|
| `common/migrations/versions/<rev>_bronze_parses.py` | Alembic migration: `bronze_parses` table |
| `pipeline/tests/fixtures/textract_responses/clean_high_confidence.json` | Captured real `AnalyzeDocument` response for the clean fixture |
| `pipeline/tests/fixtures/textract_responses/blurry_low_confidence.json` | Captured real `AnalyzeDocument` response for the blurry fixture |

## Files to Modify

| File | Changes |
|------|---------|
| `common/src/common/models.py` | Add `BronzeParse` SQLAlchemy model (for ORM-side consistency/reference, even though the Lambda itself uses raw SQL) |
| `pipeline/src/pipeline/bronze/parse_handler.py` | Replace placeholder body with real Textract + Aurora logic described above |
| `pipeline/tests/unit/test_bronze_parse_handler.py` | Replace placeholder pass-through tests with: clean-doc success, blurry-doc lower-confidence, Textract permanent-failure → `claims.status='failed'` + re-raise |
| `infra/src/infra/pipeline_stack.py` | Accept `database: rds.DatabaseCluster` param; `database.grant_data_api_access(parse_function)`; `documents_bucket.grant_read(parse_function)`; add `textract:AnalyzeDocument` IAM statement (resource `*` — Textract doesn't support resource-level perms for this action); set `AURORA_CLUSTER_ARN`/`AURORA_SECRET_ARN`/`AURORA_DATABASE_NAME` env vars on `BronzeParseFunction`; bump its timeout (15s → 60s, Textract sync calls can take a few seconds) |
| `infra/app.py` | Pass `foundation_stack.database` into `ClaimsReviewPipelineStack` |
| `infra/README.md` | Document the bronze Lambda's real behavior, the Data-API-over-raw-SQL decision, and the new table |
| `common/README.md` | Add `bronze_parses` to the schema table list |

## Tests

| Test File | Coverage |
|-----------|----------|
| `pipeline/tests/unit/test_bronze_parse_handler.py` | clean-doc parse (mocked Textract fixture + mocked rds-data) returns expected `parse_confidence`/shape; blurry-doc parse yields a lower `parse_confidence` than clean; Textract error after retries → `claims.status` update to `failed` issued and exception re-raised |
| (manual) | `alembic upgrade head` against real Aurora; `cdk deploy`; upload each of the 4 fixtures via AWS MCP presigned PUT; confirm state machine `SUCCEEDED` for each; query `claims`/`bronze_parses` via AWS MCP `call_aws` (`aws rds-data execute-statement`) to confirm real rows, and that the blurry fixture's `parse_confidence` is meaningfully lower than the clean fixture's |

## Technical Details

- `rds-data` calls use `resourceArn`, `secretArn`, `database` from the cluster construct — same three values Alembic already needs, sourced this time as Lambda environment variables rather than shell env vars
- Idempotency: both `claims` and `bronze_parses` upserts are `ON CONFLICT DO UPDATE`, so re-running the same S3 key (e.g. a retry) doesn't create duplicate rows
- `BronzeParse` ORM model added to `common/models.py` for documentation/consistency even though the Lambda bypasses it — future components (e.g. a debug/reporting script) can still use the ORM to read `bronze_parses`

## Based on Design Doc

No design doc for this item (mode is `confirm`) — plan derived from `.specs-fire/intents/claims-review-platform/work-items/06-bronze-textract-parse.md` acceptance criteria plus the two scoping decisions above.

---
*Plan awaiting approval.*
