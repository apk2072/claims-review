---
run: run-claims-review-004
work_item: pipeline-orchestration
intent: claims-review-platform
generated: 2026-07-08T01:20:00Z
mode: confirm
---

# Implementation Walkthrough: Step Functions pipeline orchestration skeleton

## Summary

Added a second CDK stack, `ClaimsReviewPipelineStack`, defining a Step Functions state machine that chains three placeholder Lambdas (bronze parse → silver classify+extract → gold confidence-route), triggered by an EventBridge rule watching the existing `DocumentsBucket` for new objects. Deployed to AWS and verified end-to-end with a real S3 upload and a successful state machine execution.

## Structure Overview

Two independent CDK stacks now compose the app: `ClaimsReviewFoundationStack` (VPC, S3, Aurora — from the prior work item) and the new `ClaimsReviewPipelineStack`, which takes a direct construct reference to the foundation stack's `documents_bucket` (same CDK app, no SSM/manual exports). The pipeline stack owns three Lambdas and a Step Functions state machine; the Lambda source code itself lives outside the CDK stack, under `pipeline/src/pipeline/{bronze,silver,gold}/`, so later work items (06/07/08) replace each handler's body without touching the orchestration wiring.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `pipeline/src/pipeline/bronze/__init__.py` | package init |
| `pipeline/src/pipeline/bronze/parse_handler.py` | placeholder bronze-parse Lambda handler (log + passthrough) |
| `pipeline/src/pipeline/silver/__init__.py` | package init |
| `pipeline/src/pipeline/silver/classify_extract_handler.py` | placeholder silver classify+extract Lambda handler |
| `pipeline/src/pipeline/gold/__init__.py` | package init |
| `pipeline/src/pipeline/gold/confidence_route_handler.py` | placeholder gold confidence-route Lambda handler |
| `infra/src/infra/pipeline_stack.py` | `ClaimsReviewPipelineStack` — 3 Lambdas, Step Functions state machine, EventBridge rule |
| `pipeline/tests/unit/test_bronze_parse_handler.py` | unit test |
| `pipeline/tests/unit/test_silver_classify_extract_handler.py` | unit test |
| `pipeline/tests/unit/test_gold_confidence_route_handler.py` | unit test |

### Modified

| File | Changes |
|------|---------|
| `infra/app.py` | Instantiate `ClaimsReviewPipelineStack`, wired to `foundation_stack.documents_bucket` |
| `infra/README.md` | Documented the new stack, manual verification steps, updated cost table and deploy/destroy commands (`--all`) |

## Key Implementation Details

### 1. Placeholder Lambdas load via `Code.from_inline`

Same technique as the existing `ConnectivityTestFunction` in the foundation stack: read the handler's `.py` source as text at synth time, embed it inline. No Docker bundling needed since these handlers are stdlib-only (`json`, `logging`). Real bronze/silver/gold implementations in later work items will likely need boto3/Bedrock clients and may switch to a proper asset-bundling approach then.

### 2. Failure isolation via shared `Fail` state

Each `LambdaInvoke` task has `.add_catch(failed_state, errors=["States.ALL"])` pointing at one `DocumentProcessingFailed` Fail state. Since every S3 upload starts its own independent state machine execution, one document's failure can't affect any other document's execution — satisfies the acceptance criterion without needing per-document Aurora bookkeeping yet (that lands with the gold-verdict-routing work item).

### 3. EventBridge over direct S3 Lambda trigger

Used an EventBridge rule (matching `aws.s3` / "Object Created", scoped to the bucket) rather than a direct S3 event notification to Lambda/Step Functions, because the bucket already had `event_bridge_enabled=True` from the foundation work item — no bucket-level changes needed, just a rule + target.

## Security Considerations

| Concern | Approach |
|---------|----------|
| IAM roles | No shared/pre-created roles — CDK auto-generates one execution role per Lambda and one role for the EventBridge rule target (least-privilege, consistent with the foundation stack's pattern) |
| Placeholder Lambda blast radius | Handlers only log + pass through — no data writes, no external calls, so there's nothing to secure yet beyond basic execution role scoping |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Lambda code location | Real `.py` files under `pipeline/src/pipeline/{bronze,silver,gold}/`, loaded inline by the CDK stack, rather than inline strings in the stack itself | Matches `coding-standards.md` file layout; lets later work items replace handler bodies without touching CDK wiring |
| State machine type | Standard (not Express) | Console-visible execution history — useful for interview demo and for this item's manual verification step |
| Lambda VPC attachment | None — placeholders run outside the VPC | They don't touch Aurora yet; avoids unnecessary ENI cold-start cost for zero benefit at this stage |
| Trigger mechanism | EventBridge rule (not direct S3→Lambda or S3→Step Functions notification) | Bucket already emits to EventBridge from the foundation work item; adding a rule is less invasive than reconfiguring bucket notifications |

## Deviations from Plan

None — implementation matched the approved plan exactly.

## Dependencies Added

None — used `aws_stepfunctions`, `aws_stepfunctions_tasks`, and `aws_events`/`aws_events_targets`, all already available via the existing `aws-cdk-lib` dependency.

## How to Verify

1. **Deploy both stacks**

   ```bash
   cd infra && JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 uv run cdk deploy --all
   ```

   Expected: `ClaimsReviewFoundation` and `ClaimsReviewPipeline` both reach `UPDATE_COMPLETE`/`CREATE_COMPLETE`.

2. **Trigger the pipeline with a fixture document**

   Upload any file from `pipeline/tests/fixtures/sample_claims/` to the `DocumentsBucket` (via AWS MCP `get_presigned_url` + PUT, or console).

3. **Check the state machine execution**

   ```bash
   aws stepfunctions list-executions --state-machine-arn <ClaimsProcessingStateMachine ARN>
   aws stepfunctions get-execution-history --execution-arn <execution ARN from above>
   ```

   Expected: one execution, `status: SUCCEEDED`; event history shows `Parse` → `ClassifyExtract` → `ConfidenceRoute`, each `TaskSucceeded`, payload unchanged at every step, ending in `ExecutionSucceeded`.

   **Actually run** 2026-07-08: confirmed exactly this — see `test-report.md` for the full trace.

## Test Coverage

- Tests added: 6 (unit)
- Coverage: 100% (on the 3 new placeholder handler modules)
- Status: passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (`infra/README.md`)
- [x] Developer notes captured

## Developer Notes

- The pipeline stack imports the bucket name from the foundation stack via a CDK cross-stack reference (`Fn::ImportValue`). Always use `cdk destroy --all` (not per-stack) so CDK handles the dependency teardown order correctly — destroying `ClaimsReviewFoundation` alone while `ClaimsReviewPipeline` still references its export will fail.
- `cdk synth` emitted an informational warning about cross-stack reference strength defaulting to "strong" — cosmetic, no action needed for a two-stack learning project.
- Next work item (`bronze-textract-parse`) will replace `BronzeParseFunction`'s handler body with real Textract calls — the Step Functions wiring, IAM, and EventBridge trigger built here should not need to change.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-004*
