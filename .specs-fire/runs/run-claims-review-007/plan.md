---
run: run-claims-review-007
work_item: gold-verdict-routing
intent: claims-review-platform
mode: confirm
checkpoint: plan
approved_at:
---

# Implementation Plan: Gold layer — auto-verdict routing

## Approach

Replace the gold placeholder Lambda with the final pipeline step: apply the auto-verdict threshold to silver's `composite_confidence`, and write the routing decision to both `extractions.is_automated` and `claims.status`.

Simpler than bronze/silver — no new AWS service call, no new fixture capture, no new dependency bundling. Same raw-SQL-over-Data-API pattern, same `Code.from_inline` deployment (stdlib + boto3 only).

**Threshold boundary decision**: `system-architecture.md`'s documented data flow already specifies `confidence > 0.92 ? yes → auto-approved`, i.e. **strictly greater than** — so exactly `0.92` routes to human review, not auto-approval. This plan follows that existing documented decision rather than introducing a new one (the work item's acceptance criteria explicitly leaves the boundary open as "documented behavior either way").

**Flow** (`pipeline/src/pipeline/gold/confidence_route_handler.py`):
1. Receive `{claim_id, extraction_id, composite_confidence}` from silver
2. `route_verdict(composite_confidence, threshold)` — pure function, `pipeline/src/pipeline/gold/verdict_routing.py`, threshold defaults to `0.92` but reads `AUTO_VERDICT_THRESHOLD` env var if set
3. `UPDATE extractions SET is_automated = :is_automated WHERE id = :extraction_id`
4. `UPDATE claims SET status = :status WHERE id = :claim_id` — `'auto_verified'` if automated, `'human_review'` otherwise (both already valid values in `common.models.CLAIM_STATUSES`) — this is what `reviewer-backend-api` will query against later
5. On any Aurora failure: mark `claims.status='failed'`, re-raise (existing Step Functions catch handles the rest) — same pattern as bronze/silver, even though gold's failure surface is much smaller (no external API besides Aurora itself)
6. Return `{claim_id, extraction_id, is_automated, composite_confidence}` — this is now the **final** state machine output

**Real-AWS action disclosure**: no new real-AWS calls beyond what's already deployed — this just changes Lambda logic and one `cdk deploy`. Manual verification re-runs all 4 fixtures end-to-end (bronze→silver→gold, using the same Textract/Bedrock calls already exercised in prior work items — no new cost category) and queries `claims`/`extractions` via the AWS MCP server to confirm final `is_automated`/`status`.

## Files to Create

| File | Purpose |
|------|---------|
| `pipeline/src/pipeline/gold/verdict_routing.py` | `DEFAULT_AUTO_VERDICT_THRESHOLD` + pure `route_verdict()` |
| `pipeline/tests/unit/test_verdict_routing.py` | Direct tests: 0.93→auto-approved, 0.91→queued, exactly 0.92→queued (documented boundary), custom threshold override |

## Files to Modify

| File | Changes |
|------|---------|
| `pipeline/src/pipeline/gold/confidence_route_handler.py` | Replace placeholder with real routing logic described above |
| `pipeline/tests/unit/test_gold_confidence_route_handler.py` | Replace placeholder pass-through tests with: above-threshold→auto_verified, at/below-threshold→human_review, Aurora failure→`claims.status='failed'`+re-raise |
| `infra/src/infra/pipeline_stack.py` | `GoldConfidenceRouteFunction` gets `database.grant_data_api_access(...)`, Aurora env vars, `AUTO_VERDICT_THRESHOLD` env var, bumped timeout |
| `infra/README.md` | Document gold's real behavior; this closes out the full pipeline description |

## Tests

| Test File | Coverage |
|-----------|----------|
| `pipeline/tests/unit/test_verdict_routing.py` | Both sides of the threshold boundary + the exact-0.92 documented case, no AWS calls |
| `pipeline/tests/unit/test_gold_confidence_route_handler.py` | Auto-approve path, human-review path, Aurora failure path (mocked `rds-data`) |
| (manual) | `cdk deploy`; re-run all 4 fixtures end-to-end (bronze→silver→gold); query `claims`/`extractions` via AWS MCP to confirm: clean → `auto_verified`/`is_automated=true`; missing-fields, wrong-type, blurry → `human_review`/`is_automated=false` |

## Technical Details

- `route_verdict(composite_confidence: float, threshold: float = DEFAULT_AUTO_VERDICT_THRESHOLD) -> bool` — `composite_confidence > threshold`
- This is the last state in the chain — its return value is what a real caller (or the future `reviewer-backend-api`) would see as the state machine's final execution output

## Based on Design Doc

No design doc for this item (mode is `confirm`) — plan derived from `.specs-fire/intents/claims-review-platform/work-items/08-gold-verdict-routing.md` acceptance criteria plus the threshold-boundary note above.

---
*Plan awaiting approval.*
