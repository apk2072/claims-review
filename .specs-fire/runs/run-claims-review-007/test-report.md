---
run: run-claims-review-007
work_item: gold-verdict-routing
intent: claims-review-platform
generated: 2026-07-08T22:25:00Z
status: passed
---

# Test Report: Gold layer — auto-verdict routing

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 7 | 0 | 0 | 100% |
| Integration | 0 | 0 | 0 | n/a |
| **Total** | 7 | 0 | 0 | 100% |

## Acceptance Criteria Validation

- ✅ **Lambda replaces the gold placeholder from work item 5** — `GoldConfidenceRouteFunction` now runs real threshold-routing logic
- ✅ **Threshold read from an environment variable / config (not hardcoded), defaulting to 0.92** — `AUTO_VERDICT_THRESHOLD` env var, `DEFAULT_AUTO_VERDICT_THRESHOLD = 0.92` fallback in `pipeline/src/pipeline/gold/verdict_routing.py`
- ✅ **`route_verdict()` pure function unit-tested on both sides of the boundary (0.93 → auto-approved, 0.91 → queued, exactly 0.92 → documented behavior either way)** — `pipeline/tests/unit/test_verdict_routing.py`, 4 tests, no AWS calls; exactly-0.92 documented as queued (strictly-greater-than), matching `system-architecture.md`
- ✅ **End-to-end manual test: all 4 synthetic fixtures flow S3 → bronze → silver → gold and land in Aurora with correct `is_automated` flags (clean doc auto-approved, blurry/missing-field docs queued)** — see Manual Verification below
- ✅ **Gold-layer Aurora row includes confidence scores, classification, extracted fields, and routing decision — everything the reviewer app needs to render** — `extractions` row (fields, field_confidences, all 4 confidence scores, is_automated) joined to `claims` (document_type, status) covers this

## Manual Verification (via AWS MCP server + local AWS CLI)

**First attempt failed** — worth recording honestly rather than glossing over: all 4 fixtures reached the shared `DocumentProcessingFailed` Fail state with `Runtime.ImportModuleError: Unable to import module 'index': No module named 'pipeline'`. Root cause: `GoldConfidenceRouteFunction` was still deployed via `Code.from_inline` (a single self-contained file), but the new handler imports a sibling module (`pipeline.gold.verdict_routing`) — that import doesn't exist in a `Code.from_inline` deployment package. Fixed by switching gold to the same `Code.from_asset` dependency-bundling helper silver already used (generalized to just vendor the whole `pipeline` package, no extra pip requirements needed for gold). Redeployed, re-tested.

**Second attempt (post-fix) — all correct**:

1. `cdk diff` confirmed only `GoldConfidenceRouteFunction` changed (env vars, IAM grant, timeout) before the first deploy attempt
2. `cdk deploy ClaimsReviewPipeline` (first attempt, then again after the bundling fix) — `UPDATE_COMPLETE` both times
3. Uploaded all 4 synthetic fixtures (fresh S3 keys) to trigger 4 independent full pipeline executions (bronze→silver→gold)
4. All 4 executions reached `SUCCEEDED`; final Aurora state:

   | Fixture | document_type | claims.status | composite_confidence | is_automated |
   |---|---|---|---|---|
   | clean | medical_claim | **auto_verified** | 0.967 | **true** |
   | missing_fields | medical_claim | **human_review** | 0.892 | **false** |
   | wrong_document_type | other | **human_review** | 0.770 | **false** |
   | blurry | other | **human_review** | 0.392 | **false** |

   Exactly matches acceptance criteria: only the clean doc (above the 0.92 threshold) auto-verified; the other three correctly queued for human review. Confirmed directly against the real `claims`/`extractions` tables via `aws rds-data execute-statement`.

All AWS verification used the AWS MCP server (`call_aws`) plus local `aws s3 cp` for uploads. `cdk deploy`/`cdk diff` ran locally as build/deploy tooling.

## Tests Written

### Unit Tests

- `pipeline/tests/unit/test_verdict_routing.py` — above/below/exactly-at threshold, custom threshold override (4 tests, no AWS calls)
- `pipeline/tests/unit/test_gold_confidence_route_handler.py` — auto-verify path, human-review path, Aurora failure marks `claims.status='failed'` and re-raises (3 tests, mocked `rds-data`)

### Integration Tests

(none — infra verified via `cdk synth`/`cdk diff` + manual deploy, consistent with prior pipeline work items)

## Test Commands

```bash
# Run all tests
uv run pytest pipeline/tests/unit/test_verdict_routing.py pipeline/tests/unit/test_gold_confidence_route_handler.py -v

# Full pipeline suite (regression check)
uv run pytest pipeline/ -v

# Infra validation
cd infra && JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 uv run cdk synth ClaimsReviewPipeline
```

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `GoldConfidenceRouteFunction` deployed via `Code.from_inline` while its handler imports a sibling module (`pipeline.gold.verdict_routing`) — every execution failed with `Runtime.ImportModuleError` | High (100% failure rate on first deploy) | **Fixed** — switched to `Code.from_asset` via the (generalized) dependency-bundling helper; re-verified all 4 fixtures pass |

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (100% on new modules; project target is 70%)
- [x] All acceptance criteria validated
- [x] No critical issues open (the one found was fixed and re-verified within this run)

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-007*
