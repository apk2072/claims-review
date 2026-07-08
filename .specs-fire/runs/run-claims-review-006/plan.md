---
run: run-claims-review-006
work_item: silver-classify-extract
intent: claims-review-platform
mode: confirm
checkpoint: plan
approved_at:
---

# Implementation Plan: Silver layer — Bedrock classify, extract, and composite confidence

## Approach

Replace the silver placeholder Lambda with real Bedrock classify + extract calls, a pure/testable composite-confidence function, and a new `extractions` row per claim.

**Model**: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (Bedrock inference profile — confirmed working via a real `invoke-model` call this session; the bare model ID errors with `ValidationException` demanding an inference-profile ARN, so the inference-profile ID is what both the Lambda and its IAM policy must reference). Haiku over Sonnet/Opus: this is a two-call-per-document, high-volume classify/extract step — cheapest capable model, consistent with the constitution's "keep AWS spend small" guidance.

**New decision — a real dependency-bundled Lambda, not `Code.from_inline`.** The acceptance criteria require Pydantic-validated structured output from the model. `pydantic-core` is a compiled (Rust) dependency, so the "no Docker" constraint that shaped bronze's raw-SQL decision applies here too — except this time it's solvable: I confirmed `pip install --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --abi cp312 --only-binary=:all: --target <dir> pydantic` successfully downloads precompiled Linux wheels from PyPI on this Mac, no Docker or Linux host needed (works because these are prebuilt wheels, not source compilation). So `pipeline_stack.py` gets a small local-bundling helper: pip-install `pydantic` into a build directory at synth time, then `lambda_.Code.from_asset(build_dir)` for the silver function only (bronze and the two remaining placeholders stay as `Code.from_inline` — no new deps needed there). Build directory goes under `infra/.build/` (added to `.gitignore` — vendored wheels shouldn't be committed).

**Data flow**: silver receives `{claim_id, bucket, key, parse_confidence}` from bronze. It reads `bronze_parses.raw_blocks` (same raw `rds-data` SQL pattern as bronze — consistent DB-access approach across pipeline Lambdas), reconstructs plain text from the `LINE` blocks, then:
1. **Classify**: Bedrock tool-use call forcing a `classify_document` tool response — `document_type` ∈ `{"medical_claim", "other"}`. Pydantic-validates the tool input.
2. **Extract** (skipped if `document_type != "medical_claim"` — no claim fields to extract from a grocery receipt): Bedrock tool-use call forcing an `extract_fields` tool response — `fields: dict[str,str]` + `field_confidences: dict[str,float]` for the 8 expected claim fields (patient_name, member_id, date_of_birth, provider_name, date_of_service, diagnosis_code, procedure_code, claim_amount). Pydantic-validates the tool input.
3. **Score**: `completeness_score` = fraction of the 8 expected fields present and non-empty; `extract_confidence` = mean of the model's self-reported field confidences (`None` if extraction was skipped); `compute_composite_score()` — pure function, no AWS calls — computes the 60/20/20 blend, with the documented edge case: if `extract_confidence` is `None`, it coalesces to `parse_confidence` (so the 60% extract weight effectively also uses parse confidence).
4. **Persist**: INSERT into `extractions` (claim_id, fields, field_confidences, parse_confidence, extract_confidence, completeness_score, composite_confidence, `is_automated=False` — `gold-verdict-routing` sets the real value later) and UPDATE `claims.document_type`.
5. **Failure handling**: same pattern as bronze — Bedrock client with adaptive retries; on permanent failure, mark `claims.status='failed'` and re-raise (existing Step Functions catch handles the rest).
6. Return `{claim_id, extraction_id, composite_confidence}` for `gold-verdict-routing`.

**Real-AWS action disclosure**: approving this plan authorizes a handful of real Bedrock `invoke-model` calls (2 for fixture capture — clean + missing-fields docs, covering the two acceptance-criteria test cases — plus up to 8 for manual verification across all 4 fixtures × 2 calls each). Haiku pricing is fractions of a cent per call. `cdk deploy` updates `ClaimsReviewPipeline` (new dependency-bundled `SilverClassifyExtractFunction`, new IAM grants). All AWS calls now go through the local `aws` CLI (the AWS MCP server disconnected this session) rather than boto3 scripts, following the same "prefer the AWS-facing tool over ad hoc scripting" spirit as before.

## Files to Create

| File | Purpose |
|------|---------|
| `pipeline/src/pipeline/silver/confidence_scoring.py` | `EXTRACT_WEIGHT`/`PARSE_WEIGHT`/`COMPLETENESS_WEIGHT` constants + pure `compute_composite_score()` |
| `pipeline/src/pipeline/silver/models.py` | Pydantic models: `ClassificationResult`, `FieldExtraction` |
| `pipeline/tests/unit/test_confidence_scoring.py` | Direct unit tests for `compute_composite_score()`, no AWS calls, including the coalescing edge case |
| `pipeline/tests/fixtures/bedrock_responses/classify_clean.json`, `extract_clean.json`, `classify_missing_fields.json`, `extract_missing_fields.json` | Captured real Bedrock tool-use responses for the two required test fixtures |

## Files to Modify

| File | Changes |
|------|---------|
| `pipeline/src/pipeline/silver/classify_extract_handler.py` | Replace placeholder with real classify+extract+score+persist logic described above |
| `pipeline/tests/unit/test_silver_classify_extract_handler.py` | Replace placeholder pass-through tests with: clean-doc (high composite score), missing-fields-doc (lower completeness → lower composite), wrong-document-type (extraction skipped), Bedrock permanent-failure → `claims.status='failed'` + re-raise |
| `infra/src/infra/pipeline_stack.py` | Add local-bundling helper (`pip install --target`); build `SilverClassifyExtractFunction` via `Code.from_asset` instead of `Code.from_inline`; grant `database.grant_data_api_access(...)`, `bedrock:InvokeModel` (resource: the Haiku inference-profile ARN) |
| `infra/app.py` | No change expected (already passes `database` in from the bronze work item) |
| `.gitignore` | Add `infra/.build/` |
| `infra/README.md` | Document the new bundling approach and the silver Lambda's real behavior |
| `common/README.md` | No schema change this work item (writes to existing `extractions` table) — note silver as an `extractions` writer |

## Tests

| Test File | Coverage |
|-----------|----------|
| `pipeline/tests/unit/test_confidence_scoring.py` | Weighted blend correctness; the `extract_confidence=None` coalescing edge case |
| `pipeline/tests/unit/test_silver_classify_extract_handler.py` | Clean doc → high composite; missing-fields doc → lower completeness/composite; wrong-document-type → extraction skipped, near-zero completeness; Bedrock permanent failure → `claims.status='failed'`, re-raise |
| (manual) | `cdk deploy`; re-run all 4 fixtures end-to-end through the full state machine (bronze→silver); query `extractions` via `aws rds-data execute-statement` to confirm rows, confirm the wrong-type fixture got `document_type='other'` and empty `fields` |

## Technical Details

- Bedrock tool-use (forced `tool_choice`) is the structured-output mechanism — more reliable than prompting for raw JSON, and Pydantic validates the tool's `input` payload before it's trusted
- `compute_composite_score(extract_confidence: float | None, parse_confidence: float, completeness_score: float) -> float` lives alone in `confidence_scoring.py` per `coding-standards.md`'s anti-pattern note against scattering thresholds — `gold-verdict-routing` will import the same weights module rather than redefining the 0.92 auto-verdict threshold elsewhere
- Local Lambda bundling only pip-installs `pydantic` (small, no transitive compiled deps beyond `pydantic-core`, which the platform/abi-targeted `pip install` resolves as a prebuilt wheel) — deliberately not reusing `common`, same reasoning as bronze

## Based on Design Doc

No design doc for this item (mode is `confirm`) — plan derived from `.specs-fire/intents/claims-review-platform/work-items/07-silver-classify-extract.md` acceptance criteria plus the two decisions above (model choice, dependency bundling).

---
*Plan awaiting approval.*
