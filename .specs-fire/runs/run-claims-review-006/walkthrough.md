---
run: run-claims-review-006
work_item: silver-classify-extract
intent: claims-review-platform
generated: 2026-07-08T22:05:00Z
mode: confirm
---

# Implementation Walkthrough: Silver layer — Bedrock classify, extract, and composite confidence

## Summary

Replaced the silver placeholder Lambda with a real implementation: two Bedrock (Claude Haiku 4.5) tool-use calls per document — classify, then extract (skipped for non-claim docs) — Pydantic-validated structured output, a pure/testable composite-confidence function, and a new `extractions` row per claim. Verified end-to-end against all 4 synthetic fixtures on real deployed infrastructure, with correctly differentiated composite scores across the full range from 0.39 (blurry) to 0.96 (clean).

## Structure Overview

`SilverClassifyExtractFunction` reads `bronze_parses.raw_blocks` for the claim (written by the prior work item), reconstructs plain text from the `LINE` blocks, and makes two Bedrock tool-use calls. The composite-confidence math is factored into its own pure module (`confidence_scoring.py`) with no AWS dependency at all, directly unit-testable. Structured-output validation lives in `models.py` as two small Pydantic models. All Aurora access is raw parameterized SQL over the RDS Data API — same pattern bronze established — rather than the `common` package's SQLAlchemy models.

The one new piece of infrastructure machinery: `pipeline_stack.py` gained a small local Lambda-bundling helper, since this is the first pipeline Lambda that needs a real third-party dependency (`pydantic`) instead of staying stdlib-only.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `pipeline/src/pipeline/silver/confidence_scoring.py` | `compute_composite_score()` + named 60/20/20 weight constants |
| `pipeline/src/pipeline/silver/models.py` | `ClassificationResult`, `FieldExtraction` Pydantic models + `EXPECTED_CLAIM_FIELDS` |
| `pipeline/tests/unit/test_confidence_scoring.py` | Direct tests for the scoring function, no AWS calls |
| `pipeline/tests/fixtures/bedrock_responses/*.json` | 4 captured real Bedrock tool-use responses (classify+extract × clean+missing-fields) |

### Modified

| File | Changes |
|------|---------|
| `pipeline/src/pipeline/silver/classify_extract_handler.py` | Placeholder → real classify+extract+score+persist logic |
| `pipeline/tests/unit/test_silver_classify_extract_handler.py` | Placeholder tests → 4 real scenario tests |
| `infra/src/infra/pipeline_stack.py` | New `_build_dependency_bundled_lambda_code()` helper; real `SilverClassifyExtractFunction` with Bedrock + Aurora IAM grants |
| `infra/README.md` | Documented silver's behavior, the bundling decision, verified results |
| `common/README.md` | Noted silver as an `extractions` writer |
| `.gitignore` | Added `infra/.build/` (vendored Lambda dependencies, not committed) |

## Key Implementation Details

### 1. Bedrock tool-use (not prompted JSON) for structured output

Both classify and extract calls use a forced `tool_choice`, so the model's response is a `tool_use` block with a schema-shaped `input` — far more reliable than asking for raw JSON in prose, and Pydantic validates that `input` before anything trusts it.

### 2. Extraction is skipped for non-claim documents

If classify returns `document_type != "medical_claim"`, the extract call never happens — `fields`/`field_confidences` stay empty, `completeness_score` is `0.0`, `extract_confidence` is `None`. Saves a Bedrock call and avoids asking the model to hallucinate claim fields out of a grocery receipt.

### 3. No-Docker dependency bundling for `pydantic`

This machine has no Docker, which is why bronze avoided the `common` package (its `psycopg[binary]` dependency needs compiled platform-specific wheels). `pydantic-core` is also compiled, but — confirmed by direct test this session — `pip install --platform manylinux2014_x86_64 --only-binary=:all:` downloads a prebuilt Linux wheel with no compilation step, so no Docker or Linux host is needed. `pipeline_stack.py`'s new helper vendors `pydantic` into `infra/.build/silver-classify-extract/` at synth time and deploys via `Code.from_asset` instead of `Code.from_inline`.

### 4. Inference profile, not the bare model ID

`aws bedrock-runtime invoke-model` with the bare model ID (`anthropic.claude-haiku-4-5-20251001-v1:0`) rejected with `ValidationException: ... Retry your request with the ID or ARN of an inference profile`. The working ID is the cross-region inference profile (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) — both the Lambda's `BEDROCK_MODEL_ID` env var and the code that called it during fixture capture use this form.

## Security Considerations

| Concern | Approach |
|---------|----------|
| IAM least-privilege | `database.grant_data_api_access()` (Aurora scoped to the specific cluster); `bedrock:InvokeModel` wildcarded deliberately — cross-region inference profiles can route to any of several underlying regions, so a tightly-scoped resource ARN would need to enumerate all of them (same tradeoff already accepted for Textract's `AnalyzeDocument` in the bronze work item) |
| No secrets in code | Bedrock model ID and Aurora connection details are environment variables / Secrets Manager, same as bronze |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Bedrock model | Claude Haiku 4.5 (inference profile) | Cheapest capable model for a 2-call-per-document classify+extract step; constitution says keep spend small |
| Structured output mechanism | Forced tool-use + Pydantic validation | More reliable than prompted JSON; satisfies the explicit acceptance criterion |
| Dependency bundling | Local pip cross-platform wheel download, not Docker | No Docker on this machine; confirmed prebuilt manylinux wheels work for `pydantic` (unlike `psycopg[binary]`) |
| Extraction skip logic | Skip Bedrock extract call entirely for non-claim docs | Saves cost/latency; avoids asking the model to invent fields for irrelevant documents |
| Aurora access | Raw parameterized SQL over Data API, no ORM | Consistency with bronze; `common`'s SQLAlchemy stack still isn't bundleable without Docker |

## Deviations from Plan

None — implementation matched the approved plan exactly, including both up-front decisions (model choice, dependency bundling).

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `pydantic` (vendored into the silver Lambda asset only, via the new bundling helper — not a `pyproject.toml` change since it was already a `pipeline` dependency for local dev/test) | Structured-output validation for Bedrock tool-use responses |

## How to Verify

1. **Deploy**

   ```bash
   cd infra && JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 uv run cdk deploy ClaimsReviewPipeline
   ```

2. **Trigger with any fixture**

   Upload a file from `pipeline/tests/fixtures/sample_claims/` to `DocumentsBucket`.

3. **Check the execution and the DB**

   ```bash
   aws stepfunctions list-executions --state-machine-arn <arn>
   aws stepfunctions describe-execution --execution-arn <arn>
   # expect: SUCCEEDED, output {"claim_id", "extraction_id", "composite_confidence"}

   aws rds-data execute-statement --resource-arn <cluster arn> --secret-arn <secret arn> \
     --database claims_review --sql "SELECT c.s3_key, c.document_type, e.composite_confidence \
     FROM claims c JOIN extractions e ON e.claim_id = c.id"
   ```

   **Actually run** 2026-07-08 against all 4 fixtures: clean 0.960, missing-fields 0.892, wrong-type 0.770, blurry 0.392 — correctly ordered, all persisted to real Aurora.

## Test Coverage

- Tests added: 8 (4 confidence-scoring unit tests, 4 handler tests)
- Coverage: 100% (new modules)
- Status: passing (14/14 across the whole `pipeline` package, including bronze/gold from prior work items)

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (`infra/README.md`, `common/README.md`)
- [x] Developer notes captured

## Developer Notes

- **The blurry fixture classified as `document_type='other'`, not `medical_claim`.** Not a bug: silver classifies from bronze's *reconstructed OCR text*, not the raw image, and that fixture's Textract output is largely illegible (`"|||||||||"`, single letters). A sufficiently garbled scan degrades classification the same way it degrades extraction — the composite score (0.392) still correctly signals "needs human review" either way, which is the behavior that actually matters downstream.
- **`us.` inference profile IDs, not bare model IDs**, are required for on-demand Bedrock invocation on this account — worth remembering before wiring up any future Bedrock caller (the assistant-agent-service and eval/GEPA work items will hit this too).
- **The no-Docker pip-bundling trick** (`--platform manylinux2014_x86_64 --only-binary=:all:`) only works for dependencies that ship prebuilt wheels with no further transitive compiled dependencies. Check any new pipeline Lambda dependency against this before assuming it'll bundle cleanly — `psycopg[binary]` was tried and rejected for exactly this reason in the bronze work item.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-006*
