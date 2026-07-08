---
run: run-claims-review-007
work_item: gold-verdict-routing
intent: claims-review-platform
generated: 2026-07-08T22:48:00Z
mode: confirm
---

# Implementation Walkthrough: Gold layer — auto-verdict routing

## Summary

Replaced the gold placeholder Lambda with the pipeline's final step: a pure threshold function (`route_verdict()`) applied to silver's `composite_confidence`, writing the routing decision to both `extractions.is_automated` and `claims.status`. This closes the full bronze→silver→gold pipeline — verified end-to-end on all 4 fixtures after fixing one deployment bug caught during manual verification.

## Structure Overview

`GoldConfidenceRouteFunction` receives `{claim_id, extraction_id, composite_confidence}` from silver, routes it through `route_verdict()` (a standalone pure function, mirroring silver's `confidence_scoring.py` pattern), then issues two Aurora updates over the RDS Data API. Same raw-SQL, no-ORM approach as bronze and silver. Its return value is the pipeline's final output — with this work item, a document dropped in S3 now produces a fully-routed Aurora row with zero human involvement.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `pipeline/src/pipeline/gold/verdict_routing.py` | `DEFAULT_AUTO_VERDICT_THRESHOLD` (0.92) + pure `route_verdict()` |
| `pipeline/tests/unit/test_verdict_routing.py` | Threshold boundary tests, no AWS calls |

### Modified

| File | Changes |
|------|---------|
| `pipeline/src/pipeline/gold/confidence_route_handler.py` | Placeholder → real routing + Aurora writes |
| `pipeline/tests/unit/test_gold_confidence_route_handler.py` | Placeholder tests → 3 real scenario tests |
| `infra/src/infra/pipeline_stack.py` | Generalized the dependency-bundling helper (was silver-only); `GoldConfidenceRouteFunction` moved to `Code.from_asset`; Aurora IAM grants + env vars |
| `infra/README.md` | Documented gold's real behavior, the generalized bundling helper, the bug found+fixed, and full end-to-end verification results |

## Key Implementation Details

### 1. Threshold boundary: strictly greater-than

`route_verdict()` returns `composite_confidence > threshold`, not `>=`. This follows `system-architecture.md`'s already-documented data flow (`confidence > 0.92 ? yes → auto-approved`) rather than introducing a new interpretation — the work item's acceptance criteria explicitly left the exact-0.92 case as "documented behavior either way," so the existing architecture doc's decision won.

### 2. Both `extractions.is_automated` and `claims.status` get updated

The work item's acceptance criteria only explicitly mention `is_automated`, but "queued for human review" needs somewhere for the reviewer app to query against later — `claims.status` transitions from `'processing'` to either `'auto_verified'` or `'human_review'` (both already valid values in `common.models.CLAIM_STATUSES` from the schema-migrations work item). This directly sets up `reviewer-backend-api`'s future "expose extraction queue" requirement.

### 3. A real bug, caught by the manual verification step (not by unit tests)

The initial implementation kept `GoldConfidenceRouteFunction` on `Code.from_inline` (matching the original placeholder's deployment), but the new handler imports a sibling module (`pipeline.gold.verdict_routing`) — an import that simply doesn't exist in a single-file `Code.from_inline` deployment package. All 4 unit tests passed fine (they run against the local `pipeline` package directly, not the deployed Lambda asset), but all 4 real executions failed identically with `Runtime.ImportModuleError: No module named 'pipeline'`. This is exactly the scenario the manual end-to-end verification step exists to catch — unit tests validate logic, not deployment packaging.

**Fix**: generalized `_build_dependency_bundled_lambda_code()` (introduced for silver's `pydantic` need) to vendor the whole `pipeline` package for any Lambda that needs sibling-module imports, regardless of whether it also needs third-party pip dependencies. Gold now uses it with an empty `requirements` list — it only needed the packaging fix, not new dependencies. Bronze stays on `Code.from_inline` since its handler genuinely has zero local imports.

## Security Considerations

| Concern | Approach |
|---------|----------|
| IAM least-privilege | `database.grant_data_api_access()` scoped to the specific Aurora cluster — same as bronze/silver |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Threshold boundary | Strictly greater-than (`>`, not `>=`) | Matches `system-architecture.md`'s already-documented data flow |
| `claims.status` update | Also set alongside `extractions.is_automated` | Acceptance criteria say "queued for human review" — needs a queryable status for the future reviewer app |
| Gold Lambda deployment | Switched to the (generalized) `Code.from_asset` bundling helper | Fixes the `ImportModuleError` found in manual verification; reuses silver's existing machinery rather than inventing a new mechanism |

## Deviations from Plan

The plan didn't anticipate gold needing the dependency-bundling helper — it assumed gold could stay on `Code.from_inline` since it needs no third-party pip dependencies. The plan missed that `Code.from_inline`'s single-file limitation applies to *any* sibling-module import, not just third-party packages. Caught during the plan's own manual-verification step, fixed within this run (see Issues Found in `test-report.md`), and re-verified — no scope change to the work item itself, just a packaging correction.

## Dependencies Added

None.

## How to Verify

1. **Deploy**

   ```bash
   cd infra && JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 uv run cdk deploy ClaimsReviewPipeline
   ```

2. **Trigger with any fixture, wait for the full chain**

   Upload a file from `pipeline/tests/fixtures/sample_claims/` to `DocumentsBucket`.

3. **Check the final state**

   ```bash
   aws stepfunctions describe-execution --execution-arn <arn>
   # expect: SUCCEEDED, output {"claim_id", "extraction_id", "is_automated", "composite_confidence"}

   aws rds-data execute-statement --resource-arn <cluster arn> --secret-arn <secret arn> \
     --database claims_review --sql "SELECT c.s3_key, c.status, e.is_automated, e.composite_confidence \
     FROM claims c JOIN extractions e ON e.claim_id = c.id"
   ```

   **Actually run** 2026-07-08 against all 4 fixtures (after the packaging fix): clean → `auto_verified`/`true` (0.967); missing-fields, wrong-type, blurry → `human_review`/`false` (0.892, 0.770, 0.392 respectively).

## Test Coverage

- Tests added: 7 (4 threshold-routing unit tests, 3 handler tests)
- Coverage: 100% (new modules)
- Status: passing (19/19 across the whole `pipeline` package)

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues (one found during manual verification, fixed and re-verified within this run)
- [x] Documentation updated (`infra/README.md`)
- [x] Developer notes captured

## Developer Notes

- **Any pipeline Lambda whose handler imports a sibling module needs `Code.from_asset` via `_build_dependency_bundled_lambda_code()`, not `Code.from_inline`** — this bit gold despite gold needing zero new dependencies. `Code.from_inline` is only safe for handlers that are genuinely self-contained (stdlib + boto3, no local imports at all), which after this work item is just bronze.
- The pipeline is now demoable end-to-end: drop any of the 4 fixtures in `DocumentsBucket` and watch it land in `claims`/`extractions` fully routed, no human step. Good checkpoint before starting `reviewer-backend-api` (per this work item's technical notes).
- Both `extractions.is_automated` and `claims.status` now carry the routing decision — redundant by design, since the reviewer app will likely query by `claims.status` (queue view) while individual field-level detail lives on `extractions`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-007*
