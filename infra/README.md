# infra

AWS CDK (Python) app defining all infrastructure: VPC, S3, Aurora Serverless v2, IAM, Step Functions, ECS Fargate services, etc.

## AWS account / bootstrap status

- AWS identity confirmed via `aws sts get-caller-identity` — default profile resolves to account `942093019462`, region `us-east-1`.
- CDK bootstrap status: **already bootstrapped** — `CDKToolkit` CloudFormation stack exists in `us-east-1` (`UPDATE_COMPLETE`). No bootstrap step needed before deploys.
- Note: CDK's underlying jsii runtime warns about untested Node.js versions on this machine (Node 25). Cosmetic only — set `JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1` to silence it.

## `ClaimsReviewFoundationStack` (deployed)

Provisions the shared foundation every other component depends on:

- **VPC** (`10.0.0.0/16`, 2 AZs): public, private-with-egress, and isolated subnet groups; 1 NAT Gateway
- **S3 bucket** (`DocumentsBucket`): SSE-S3 encrypted, Block Public Access, EventBridge notifications enabled, `removal_policy=DESTROY` + `auto_delete_objects=True` (so `cdk destroy` fully tears down — a real production bucket would use `RETAIN`)
- **Aurora Serverless v2 Postgres 16.13** (`AuroraCluster`): single instance, single-AZ, isolated subnet, min 0 / max 2 ACU (scale-to-zero), Secrets Manager-managed credentials, `enable_data_api=True`, pgvector 0.8.1 confirmed installed
- **ConnectivityTestFunction**: a small stdlib-only Lambda (no compiled DB driver — Docker isn't available on this machine for bundling) that speaks just enough of the Postgres wire protocol (an SSLRequest) to prove the VPC/security-group path from a private-with-egress subnet actually reaches Aurora in the isolated subnet. Left in place as a reusable debug tool — re-run any time VPC/SG connectivity is suspected of being broken:
  ```bash
  aws lambda invoke --function-name <ConnectivityTestFunctionName from outputs> /tmp/out.json && cat /tmp/out.json
  # expect: {"reachable": true, ..., "postgres_ssl_reply": "S"}
  ```
- No IAM roles are pre-created for future services. Each Lambda/Fargate task added in later work items gets its own CDK-auto-generated execution role, with permissions attached incrementally via `grant*()` calls at the point that resource is defined.

Verified: `cdk synth`, `cdk deploy` (full create + a targeted redeploy), pgvector extension via RDS Data API, VPC connectivity via the test Lambda, and a full `cdk destroy` + `cdk deploy` teardown/rebuild cycle.

## `ClaimsReviewPipelineStack` (deployed)

Step Functions orchestration skeleton — proves the bronze/silver/gold wiring shape before the real Textract/Bedrock logic lands in later work items:

- **3 placeholder Lambdas** (`BronzeParseFunction`, `SilverClassifyExtractFunction`, `GoldConfidenceRouteFunction`): stdlib-only, log the input event and pass it through unchanged. Source lives at `pipeline/src/pipeline/{bronze,silver,gold}/*_handler.py` and is loaded via `Code.from_inline` (same no-Docker-available approach as `ConnectivityTestFunction`). None are VPC-attached — they don't touch Aurora yet.
- **`ClaimsProcessingStateMachine`** (Standard): `Parse` → `ClassifyExtract` → `ConfidenceRoute`, each task with `.add_catch(..., errors=["States.ALL"])` routed to a shared `DocumentProcessingFailed` Fail state, so one document's failure doesn't affect others (each S3 event is its own execution).
- **`DocumentIngestRule`** (EventBridge): matches `aws.s3` / "Object Created" scoped to `DocumentsBucket` (already EventBridge-enabled from the foundation stack), targets the state machine. CDK auto-grants the rule's role `states:StartExecution`.

Manual test (via AWS MCP server — `get_presigned_url` + `call_aws`, not local CLI):
```bash
# 1. Presign + PUT a fixture into DocumentsBucket (any key under claims/)
# 2. aws stepfunctions list-executions --state-machine-arn <arn from stack>
# 3. aws stepfunctions get-execution-history --execution-arn <arn from step 2>
#    expect: ExecutionStarted -> Parse/ClassifyExtract/ConfidenceRoute all TaskSucceeded -> ExecutionSucceeded
```
Verified 2026-07-08: one execution, all 3 states `TaskSucceeded`, payload passed through unchanged at each step, `ExecutionSucceeded`.

## Cost estimate (always-on pieces, if left running)

| Resource | Approx. cost | Notes |
|---|---|---|
| NAT Gateway | ~$32-38/mo + ~$0.045/GB processed | Biggest always-on cost. Only way to avoid it entirely would be 5+ VPC interface endpoints, which cost more at this scale (see design doc) |
| Aurora Serverless v2 (min 0 ACU) | ~$0 when scaled to zero; ~$0.12/ACU-hour while active | Scale-to-zero means idle time between practice sessions costs nothing but storage; expect a ~15-30s cold-start resuming from zero (confirmed: got a `DatabaseResumingException` on the first Data API call, succeeded on retry) |
| Step Functions + placeholder Lambdas | Negligible, pay-per-use | ~$0.025/1,000 state transitions; Lambda invocations well within free tier at demo scale; no always-on cost |
| S3, Secrets Manager, CloudWatch Logs | Negligible | Well under $1/mo at this scale |

**Bottom line: the NAT Gateway is the only real always-on cost. Run `cdk destroy` between practice sessions to avoid accruing it.**

## Commands

```bash
cdk synth              # synthesize CloudFormation template(s)
cdk diff                # show changes vs. deployed stacks
cdk deploy --all        # deploy both stacks (real AWS resources / real cost from this point on)
cdk destroy --all       # tear down both stacks — use this between practice sessions to control cost
```

`ClaimsReviewPipelineStack` imports `DocumentsBucket`'s name from `ClaimsReviewFoundationStack` via a CDK cross-stack reference — `cdk destroy --all` (not per-stack) handles the dependency ordering correctly.

Runs via `uv run python app.py` under the hood (see `cdk.json`), using the shared workspace virtualenv.
