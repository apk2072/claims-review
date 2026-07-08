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

Full bronze→silver→gold document pipeline — closes the loop from S3 upload to a fully-routed Aurora row:

- **`BronzeParseFunction`** (real, `bronze-textract-parse`): calls Amazon Textract `AnalyzeDocument` (FORMS) on the incoming S3 object, then writes to Aurora over the **RDS Data API using raw parameterized SQL** — not the `common` package's SQLAlchemy models. `common` pulls in `psycopg[binary]` (a compiled dependency), and this Lambda is still deployed via `Code.from_inline` with no Docker-based bundling available on this machine (same constraint as `ConnectivityTestFunction`). The Data API is also how Alembic already reaches this cluster from outside the VPC, so this Lambda stays VPC-unattached too. Retries transient Textract errors via boto3's adaptive retry config; on permanent failure, marks `claims.status = 'failed'` and re-raises so the state machine's existing catch handles the rest.
- **`SilverClassifyExtractFunction`** (real, `silver-classify-extract`): reconstructs plain text from `bronze_parses.raw_blocks`, then calls Bedrock (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) twice — once to classify (`medical_claim` vs `other`, tool-use forced, Pydantic-validated), once to extract fields+confidences (skipped if not classified as a claim). Computes `compute_composite_score()` (60% extract / 20% parse / 20% completeness — see `pipeline/src/pipeline/silver/confidence_scoring.py`) and writes an `extractions` row. Bedrock's bare model ID rejects on-demand invocation (`ValidationException: ... Retry your request with the ID or ARN of an inference profile`) — the cross-region inference profile ID is what's actually invoked, and `bedrock:InvokeModel` is granted on `*` since the profile can route to any of several underlying regions.
- **`GoldConfidenceRouteFunction`** (real, `gold-verdict-routing`): applies `route_verdict()` (`pipeline/src/pipeline/gold/verdict_routing.py`) — strictly-greater-than the `AUTO_VERDICT_THRESHOLD` env var (default `0.92`, per `system-architecture.md`'s documented data flow; exactly `0.92` does **not** auto-approve) — to silver's `composite_confidence`. Updates `extractions.is_automated` and `claims.status` (`'auto_verified'` or `'human_review'`), and returns the final `{claim_id, extraction_id, is_automated, composite_confidence}` state machine output. This is the pipeline's last state.

**Dependency bundling, generalized**: all three real Lambdas share Aurora access over the Data API using raw SQL (avoiding `common`'s compiled `psycopg[binary]`), and both silver and gold need to import sibling modules (`pipeline.silver.confidence_scoring`, `pipeline.gold.verdict_routing`) that don't fit in a single `Code.from_inline` file. `pipeline_stack.py`'s `_build_dependency_bundled_lambda_code()` helper vendors the whole `pipeline` package into a per-Lambda build directory (`infra/.build/<name>/`, gitignored) and deploys via `Code.from_asset`; it optionally also pip-installs pure-manylinux-wheel third-party deps (just `pydantic`, for silver) with no Docker needed — `pip install --platform manylinux2014_x86_64 --only-binary=:all:` downloads prebuilt Linux wheels directly, confirmed working this session. Only bronze stays on `Code.from_inline`, since its handler is fully self-contained (stdlib + boto3 only).

**Bug caught during gold's manual verification**: gold was initially deployed via `Code.from_inline` (like the original placeholder) even though its handler imports `pipeline.gold.verdict_routing` — every execution failed with `Runtime.ImportModuleError: No module named 'pipeline'`. Fixed by switching gold to the same `Code.from_asset` bundling helper as silver (with no extra pip requirements, since gold only needs boto3). Re-verified clean after the fix — see below.

- **`ClaimsProcessingStateMachine`** (Standard): `Parse` → `ClassifyExtract` → `ConfidenceRoute`, each task with `.add_catch(..., errors=["States.ALL"])` routed to a shared `DocumentProcessingFailed` Fail state, so one document's failure doesn't affect others (each S3 event is its own execution).
- **`DocumentIngestRule`** (EventBridge): matches `aws.s3` / "Object Created" scoped to `DocumentsBucket` (already EventBridge-enabled from the foundation stack), targets the state machine. CDK auto-grants the rule's role `states:StartExecution`.

Manual test (via AWS MCP server — `get_presigned_url`/local `aws s3 cp` + `call_aws`):
```bash
# 1. Upload a fixture into DocumentsBucket (any key under claims/)
# 2. aws stepfunctions list-executions --state-machine-arn <arn from stack>
# 3. aws stepfunctions describe-execution --execution-arn <arn from step 2>
#    expect: status SUCCEEDED, output {"claim_id", "extraction_id", "is_automated", "composite_confidence"}
# 4. aws rds-data execute-statement --resource-arn <cluster arn> --secret-arn <secret arn> \
#      --database claims_review --sql "SELECT c.s3_key, c.document_type, c.status, \
#      e.composite_confidence, e.is_automated FROM claims c JOIN extractions e ON e.claim_id = c.id"
```
Verified 2026-07-08 (pipeline-orchestration): one execution, all 3 states `TaskSucceeded`, payload passed through unchanged at each step, `ExecutionSucceeded`.

Verified 2026-07-08 (silver-classify-extract): all 4 synthetic fixtures run end-to-end (bronze→silver) with correctly differentiated composite confidence — clean 0.96, missing-fields 0.89, wrong-document-type 0.77 (extraction correctly skipped, `document_type='other'`), blurry 0.39 (lowest, correctly destined for human review). Notably the blurry fixture's OCR output was garbled enough that Bedrock classified it as `'other'` too, not `'medical_claim'` — not a bug: silver classifies from bronze's *reconstructed text*, not the raw image, so a sufficiently illegible scan degrades classification the same way it degrades extraction. The composite score still correctly lands well below the auto-verdict threshold either way.

Verified 2026-07-08 (gold-verdict-routing): full bronze→silver→gold run on all 4 fixtures. Final `claims.status`/`extractions.is_automated`: clean → `auto_verified`/`true` (composite 0.967 > 0.92); blurry, missing-fields, wrong-document-type → `human_review`/`false`. This is the last pipeline work item — a document dropped in S3 now flows to a fully-routed Aurora row with no human involvement.

## Cost estimate (always-on pieces, if left running)

| Resource | Approx. cost | Notes |
|---|---|---|
| NAT Gateway | ~$32-38/mo + ~$0.045/GB processed | Biggest always-on cost. Only way to avoid it entirely would be 5+ VPC interface endpoints, which cost more at this scale (see design doc) |
| Aurora Serverless v2 (min 0 ACU) | ~$0 when scaled to zero; ~$0.12/ACU-hour while active | Scale-to-zero means idle time between practice sessions costs nothing but storage; expect a ~15-30s cold-start resuming from zero (confirmed: got a `DatabaseResumingException` on the first Data API call, succeeded on retry) |
| Step Functions + Lambdas | Negligible, pay-per-use | ~$0.025/1,000 state transitions; Lambda invocations well within free tier at demo scale; no always-on cost |
| Textract (`AnalyzeDocument` FORMS) | ~$0.05/page | Single-page synthetic fixtures; a handful of test runs costs cents |
| Bedrock (Claude Haiku 4.5, 2 calls/doc) | Fractions of a cent/doc | Cheapest capable model for a two-call-per-document classify+extract step |
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
