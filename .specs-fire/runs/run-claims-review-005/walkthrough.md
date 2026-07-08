---
run: run-claims-review-005
work_item: bronze-textract-parse
intent: claims-review-platform
generated: 2026-07-08T01:53:00Z
mode: confirm
---

# Implementation Walkthrough: Bronze layer — Textract document parsing

## Summary

Replaced the bronze-parse placeholder Lambda with a real implementation that calls Amazon Textract `AnalyzeDocument` (FORMS) on the incoming S3 object and persists the result to a new `bronze_parses` Aurora table over the RDS Data API, using raw parameterized SQL rather than the `common` package's ORM. Verified end-to-end against real AWS infrastructure with all 4 synthetic fixtures plus a real permanent-failure case, and fixed a genuine Aurora cold-start bug discovered during that verification.

## Structure Overview

The Lambda (`pipeline/src/pipeline/bronze/parse_handler.py`) is self-contained: two boto3 clients (`textract`, `rds-data`), no ORM, no ODBC-style driver, deployed via the same `Code.from_inline` mechanism as the other pipeline placeholders. It upserts a `claims` row for the S3 key, calls Textract, then upserts a `bronze_parses` row with the trimmed blocks and a computed confidence score. On any Textract failure (after boto3's own adaptive retries are exhausted), it marks the claim `failed` and re-raises, letting the state machine's existing `.add_catch()` (from `pipeline-orchestration`) route to the shared `DocumentProcessingFailed` state.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `common/migrations/versions/c1fc63bb75f0_bronze_parses.py` | Alembic migration: `bronze_parses` table |
| `pipeline/tests/fixtures/textract_responses/clean_high_confidence.json` | Captured real `AnalyzeDocument` response, clean fixture |
| `pipeline/tests/fixtures/textract_responses/blurry_low_confidence.json` | Captured real `AnalyzeDocument` response, blurry fixture |

### Modified

| File | Changes |
|------|---------|
| `common/src/common/models.py` | Added `BronzeParse` ORM model (documentation/consistency; the Lambda itself bypasses it) |
| `common/README.md` | Documented `bronze_parses` in the schema list |
| `pipeline/src/pipeline/bronze/parse_handler.py` | Full real implementation: Textract call, Aurora upserts, retry logic |
| `pipeline/tests/unit/test_bronze_parse_handler.py` | 4 tests: clean, blurry (lower confidence), permanent Textract failure, Aurora resume-retry |
| `infra/src/infra/pipeline_stack.py` | `database` constructor param, `grant_data_api_access`, S3 read grant, `textract:AnalyzeDocument` IAM statement, env vars, 60s timeout |
| `infra/app.py` | Pass `foundation_stack.database` into the pipeline stack |
| `infra/README.md` | Documented the real bronze Lambda, the Data-API-over-ORM decision, updated manual test steps |

## Key Implementation Details

### 1. New `bronze_parses` table, not a `claims`/`extractions` column

Textract's raw per-element blocks are a distinct, potentially large artifact from both `claims` (lean identity row) and `extractions` (later structured field/verdict). Keeping it in its own table, joined 1:1 by `claim_id`, keeps both of those tables clean.

### 2. Raw `rds-data` SQL in the Lambda, not the `common` ORM

`pipeline/pyproject.toml` already depends on `common`, which pulls in `psycopg[binary]` — a compiled dependency. This machine still has no Docker for Lambda asset bundling (same constraint documented for `ConnectivityTestFunction`). So the Lambda talks to Aurora via parameterized SQL over the RDS Data API directly, staying dependency-free and VPC-unattached, deployed via the existing `Code.from_inline` pattern. This mirrors how Alembic already reaches this cluster from outside the VPC.

### 3. Textract fixture capture, not moto

Confirmed `moto` (5.2.2) doesn't implement `textract.analyze_document` (raises `NotImplementedError`) and its `rds-data` mock always returns empty `records`. Per `testing-standards.md`, captured 2 real Textract responses as JSON fixtures and mocked the boto3 clients directly in unit tests instead.

### 4. Aurora cold-start retry (found during manual verification, not planned upfront)

The first real end-to-end verification attempt failed all 4 fixtures with `DatabaseResumingException` — Aurora's scale-to-zero cold start, previously only encountered in manual `alembic`/test runs where a human just retries. In production (S3-triggered), nothing retries automatically. Added a bounded retry (one retry, 15s wait) around `rds-data` calls specifically for this error code, with a regression test, then redeployed and reverified.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Bronze output storage | New `bronze_parses` table | Keeps raw Textract blocks separate from `claims` identity and `extractions` verdict data |
| DB access from Lambda | Raw `rds-data` SQL, not `common`'s SQLAlchemy models | Avoids Docker-based bundling for `common`'s compiled deps on this machine; matches Alembic's existing Data-API pattern |
| Test fixtures | Captured real Textract responses, mocked boto3 directly | `moto` doesn't implement `analyze_document`; matches `testing-standards.md` guidance |
| Aurora cold-start handling | One bounded retry (15s) on `DatabaseResumingException` inside the handler | Found necessary during manual verification — nothing else would retry a production S3-triggered invocation |

## Deviations from Plan

One addition beyond the approved plan: the Aurora resume-retry logic and its regression test. Not in the original plan because the cold-start issue only surfaced during manual verification; fixed within the same run rather than deferring, since without it the acceptance criterion "successfully parses all 4 fixtures" did not actually hold on the first deploy.

## Dependencies Added

None — used `boto3` (already a `pipeline` dependency) and `botocore.exceptions.ClientError`/`botocore.config.Config`, both part of `boto3`'s existing dependency footprint.

## How to Verify

1. **Run the migration and confirm the table**

   ```bash
   export AURORA_CLUSTER_ARN=... AURORA_SECRET_ARN=... AURORA_DATABASE_NAME=claims_review
   uv run --package common alembic -c common/alembic.ini upgrade head
   ```

2. **Deploy and trigger with a fixture**

   Upload a fixture to `DocumentsBucket`, then:
   ```bash
   aws stepfunctions list-executions --state-machine-arn <arn>
   aws rds-data execute-statement --resource-arn <cluster arn> --secret-arn <secret arn> \
     --database claims_review --sql "SELECT s3_key, status FROM claims"
   ```
   Expected: execution `SUCCEEDED`, a `claims` row with `status='processing'`, a matching `bronze_parses` row with a plausible `parse_confidence`.

3. **Actually run** (2026-07-08): all 4 fixtures produced real rows — clean 0.985, missing-fields 0.985, wrong-type 0.962, blurry **0.490**. A direct nonexistent-key execution confirmed the failure path: `claims.status='failed'`, state machine reached `DocumentProcessingFailed` cleanly.

## Test Coverage

- Tests added: 4 (unit; net total in this file: 4, replacing the prior 2 placeholder tests)
- Coverage: 100% (bronze handler module)
- Status: passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues (found issue fixed within this run)
- [x] Documentation updated (`infra/README.md`, `common/README.md`)
- [x] Developer notes captured

## Developer Notes

- **Any new Lambda that talks to Aurora over the Data API should wrap its `execute_statement` calls the same way** (`_execute_statement` in `parse_handler.py`) — the cold-start `DatabaseResumingException` will recur for `silver-classify-extract` and `gold-verdict-routing` too, since they'll hit the same cluster. Worth factoring into a shared helper once a second Lambda needs it (not done here — premature to extract for one caller).
- `bronze_parses.claim_id` is `UNIQUE`, so re-processing the same S3 key (e.g. after a retry) overwrites the existing row rather than creating duplicates — same idempotency pattern as the `claims` upsert.
- Textract's synchronous `AnalyzeDocument` needs `textract:AnalyzeDocument` granted on resource `"*"` — it doesn't support resource-level permissions, unlike most other AWS APIs used in this project so far.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-005*
