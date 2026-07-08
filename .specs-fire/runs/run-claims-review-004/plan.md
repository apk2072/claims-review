---
run: run-claims-review-004
work_item: pipeline-orchestration
intent: claims-review-platform
mode: confirm
checkpoint: plan
approved_at:
---

# Implementation Plan: Step Functions pipeline orchestration skeleton

## Approach

Add a second CDK stack (`ClaimsReviewPipelineStack`) alongside the existing `ClaimsReviewFoundationStack`, instantiated in the same CDK app so it can take a direct construct reference to the foundation stack's `documents_bucket` (no cross-stack exports/SSM needed — same app, same synth).

The stack defines:
1. **Three placeholder Lambdas** (bronze parse, silver classify+extract, gold confidence-route) — stdlib-only, logs the input event as JSON and returns it unchanged. Loaded via `Code.from_inline(path.read_text())`, same pattern already used for `ConnectivityTestFunction` in the foundation stack (no Docker available on this machine for asset bundling, and these placeholders have zero third-party deps). None of the three need VPC attachment — they don't touch Aurora yet, so keeping them outside the VPC avoids ENI cold-start cost for no benefit.
2. **A Step Functions Standard state machine** chaining the three as `LambdaInvoke` tasks: `Parse` → `ClassifyExtract` → `ConfidenceRoute` → `Succeed`. Each task gets `.add_catch(..., errors=["States.ALL"])` routed to one shared `Fail` state (`DocumentProcessingFailed`), so one task's failure doesn't hang the execution and doesn't affect other document executions (each S3 event starts its own independent execution).
3. **An EventBridge rule** matching S3 "Object Created" events scoped to `documents_bucket` (the bucket already has `event_bridge_enabled=True` from the foundation work item, so this is just a rule + target, no bucket changes) with the state machine as target. CDK auto-grants the rule's IAM role `states:StartExecution` on the state machine.

The actual bronze/silver/gold Lambda source files land under `pipeline/src/pipeline/{bronze,silver,gold}/` per `coding-standards.md`'s file layout (`pipeline/bronze/`, `pipeline/silver/`, `pipeline/gold/` — "one Lambda handler per file"), not inline in the CDK stack, so work items 06/07/08 can replace each placeholder body in place without touching the CDK stack's wiring.

Deliberately no Aurora write, no real Textract/Bedrock calls, no retry tuning — this item only proves the orchestration shape end-to-end, per the work item's technical notes.

**Real-AWS action disclosure**: approving this plan authorizes running `cdk deploy` (new: 3 Lambdas, 1 state machine, 1 EventBridge rule — all pay-per-use, no always-on cost) and one manual test execution (uploading a small fixture file to the existing `DocumentsBucket`, which triggers one real Step Functions execution + 3 Lambda invocations — negligible cost, well under $0.01). All AWS read/verification calls (describe stack, describe state machine, start/describe execution, S3 put/list) will go through the AWS MCP server (`aws-mcp`) rather than local `aws` CLI/boto3, per your instruction. `cdk deploy`/`cdk synth` itself still runs locally (it's a build tool, not a raw AWS API call) using this machine's already-bootstrapped CDK credentials.

## Files to Create

| File | Purpose |
|------|---------|
| `pipeline/src/pipeline/bronze/__init__.py` | package init |
| `pipeline/src/pipeline/bronze/parse_handler.py` | placeholder bronze-parse Lambda handler (logs event, passes through) |
| `pipeline/src/pipeline/silver/__init__.py` | package init |
| `pipeline/src/pipeline/silver/classify_extract_handler.py` | placeholder silver classify+extract Lambda handler |
| `pipeline/src/pipeline/gold/__init__.py` | package init |
| `pipeline/src/pipeline/gold/confidence_route_handler.py` | placeholder gold confidence-route Lambda handler |
| `infra/src/infra/pipeline_stack.py` | `ClaimsReviewPipelineStack` — 3 Lambdas, Step Functions state machine, EventBridge rule |
| `pipeline/tests/unit/test_bronze_parse_handler.py` | unit test: pass-through + logging behavior |
| `pipeline/tests/unit/test_silver_classify_extract_handler.py` | unit test: pass-through + logging behavior |
| `pipeline/tests/unit/test_gold_confidence_route_handler.py` | unit test: pass-through + logging behavior |

## Files to Modify

| File | Changes |
|------|---------|
| `infra/app.py` | Instantiate `ClaimsReviewPipelineStack`, passing `foundation_stack.documents_bucket` |
| `infra/README.md` | Document new stack, state machine name/ARN convention, manual test command (via AWS MCP), updated cost note (negligible: Step Functions ~$0.025/1000 transitions, placeholder Lambdas within free tier) |

## Tests

| Test File | Coverage |
|-----------|----------|
| `pipeline/tests/unit/test_bronze_parse_handler.py` | handler returns input event unchanged, doesn't raise |
| `pipeline/tests/unit/test_silver_classify_extract_handler.py` | same |
| `pipeline/tests/unit/test_gold_confidence_route_handler.py` | same |
| (manual) | `cdk deploy`, then upload a fixture from `pipeline/tests/fixtures/sample_claims/` to `DocumentsBucket` via AWS MCP `call_aws` (`aws s3api put-object`), then poll the state machine execution via AWS MCP (`aws stepfunctions list-executions` / `describe-execution`) until `SUCCEEDED`, confirming all 3 states ran |

`cdk synth` acts as the infra "test" (no infra unit test framework in place yet, consistent with `foundation_stack.py` which also has no unit tests — verified by synth + manual deploy instead).

## Technical Details

- State machine type: **Standard** (not Express) — gives console visibility into per-execution history, useful for interview demo and for debugging the manual test
- IAM: no shared roles — CDK auto-generates one execution role per Lambda and one role for the EventBridge rule target, exactly matching the foundation stack's established least-privilege pattern
- Placeholder handler shape (all three identical except log message):
  ```python
  import json
  import logging

  logger = logging.getLogger()
  logger.setLevel(logging.INFO)

  def handler(event, context):
      logger.info(json.dumps({"stage": "bronze-parse", "event": event}))
      return event
  ```
- EventBridge rule pattern:
  ```python
  event_pattern=events.EventPattern(
      source=["aws.s3"],
      detail_type=["Object Created"],
      detail={"bucket": {"name": [documents_bucket.bucket_name]}},
  )
  ```

## Based on Design Doc

No design doc for this item (mode is `confirm`, not `validate`) — plan derived directly from `.specs-fire/intents/claims-review-platform/work-items/05-pipeline-orchestration.md` acceptance criteria.

---
*Plan awaiting approval.*
