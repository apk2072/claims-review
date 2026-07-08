---
run: run-claims-review-002
work_item: aws-foundation-infra
intent: claims-review-platform
generated: 2026-07-07T00:32:00.000Z
status: passed
---

# Test Report: AWS foundation infrastructure (VPC, S3, IAM, Aurora cluster)

## Summary

All verification is against real deployed AWS resources — no mocks, since this work item's entire purpose is proving the infrastructure actually works. Two deploy issues were hit and fixed during implementation (see Issues Found); all acceptance criteria pass on the final deployed stack, including a full destroy/rebuild cycle.

| Check | Result |
|---|---|
| `cdk synth` | ✅ synthesizes cleanly |
| `cdk deploy` (initial) | ❌ failed — non-ASCII em-dash in `SecurityGroup` description (EC2 requires ASCII); auto-rolled back cleanly, no leftover resources |
| Fix + `cdk deploy` (retry) | ✅ all 48 resources created successfully |
| pgvector extension via RDS Data API | ✅ `CREATE EXTENSION IF NOT EXISTS vector;` succeeded (after one `DatabaseResumingException` cold-start retry); confirmed version `0.8.1` |
| VPC→Aurora connectivity via test Lambda | ✅ (after fixing the handler's blind `recv()` bug) TCP connect + Postgres SSLRequest exchange succeeded, reply `"S"` |
| `cdk destroy` | ✅ all 48 resources deleted cleanly |
| `cdk deploy` (rebuild) | ✅ all resources recreated |
| pgvector + connectivity re-verified post-rebuild | ✅ both pass again on the fresh cluster/Lambda |
| `uv run ruff check infra/` / `ruff format --check infra/` | ✅ clean throughout |

## Acceptance Criteria Validation

- ✅ **`cdk deploy` provisions VPC, S3 bucket, Aurora Serverless v2 cluster (min/max ACU for cost)** — min 0 / max 2 ACU, scale-to-zero confirmed via cold-start behavior
- ✅ **S3 bucket has event notification configuration ready to target a Lambda** — `event_bridge_enabled=True`, no target wired yet (deferred to `pipeline-orchestration` as planned)
- ✅ **Aurora reachable only from within the VPC; pgvector confirmed via one-off connection** — no public endpoint (isolated subnet, no route to internet); pgvector 0.8.1 confirmed via RDS Data API
- ✅ **IAM roles for Lambda/ECS created with least-privilege placeholders** — deviation approved in design doc: no shared roles pre-created; each compute resource gets its own CDK-auto-generated execution role with `grant*()`-based permissions added incrementally. `ConnectivityTestFunction`'s auto-generated execution role is the first example of this pattern.
- ✅ **Documented, one-command teardown path exists and is tested once** — `cdk destroy`, tested twice (once implicitly via the failed-deploy rollback, once explicitly as a full destroy → redeploy cycle)
- ✅ **Approximate monthly cost of always-on pieces written down in infra/README.md** — NAT Gateway (~$32-38/mo) called out as the dominant always-on cost; Aurora near-$0 when scaled to zero

## Tests Written

### Unit Tests

(none — infrastructure-definition code; correctness is verified by actual deployment, not unit tests, per `testing-standards.md`'s manual/E2E category for this kind of change)

### Integration Tests

(none — see manual verification above)

## Test Commands

```bash
# Lint
uv run ruff check infra/
uv run ruff format --check infra/

# Deploy / verify / teardown cycle
cd infra
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk synth
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk deploy --require-approval never --outputs-file /tmp/cdk-outputs.json

aws rds-data execute-statement --resource-arn <cluster-arn> --secret-arn <secret-arn> \
  --database claims_review --sql "CREATE EXTENSION IF NOT EXISTS vector;"
aws rds-data execute-statement --resource-arn <cluster-arn> --secret-arn <secret-arn> \
  --database claims_review --sql "SELECT extversion FROM pg_extension WHERE extname = 'vector';"

aws lambda invoke --function-name <ConnectivityTestFunctionName> /tmp/out.json && cat /tmp/out.json

JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk destroy --force
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk deploy --require-approval never
```

## Coverage Details

Not applicable — infrastructure code, no unit test coverage target per `testing-standards.md`.

## Issues Found

| Issue | Severity | Status |
|---|---|---|
| EC2 `SecurityGroup` `description` rejected non-ASCII em-dash characters, failing initial deploy | medium (blocked first deploy, but rolled back cleanly with zero leftover resources) | fixed — replaced em-dashes with hyphens in both security group descriptions |
| `test_connectivity_handler.py` blindly called `sock.recv(64)` expecting an unsolicited server banner; Postgres doesn't send one (client speaks first), causing a false-negative timeout | medium (would have been misread as a connectivity failure) | fixed — handler now sends a minimal Postgres `SSLRequest` message and checks for the single-byte `S`/`N` reply, which also more rigorously proves a real Postgres server answered, not just an open port |
| No Docker available on this machine, so a `PythonFunction` (Lambda + pip-installed `psycopg`) wasn't viable for the connectivity test | low (design adjustment, not a defect) | worked around by splitting verification: stdlib-only Lambda for the network-path check, RDS Data API for the pgvector/SQL check — documented in `test_connectivity_handler.py`'s docstring and `infra/README.md` |

## Ready for Completion

- [x] All tests passing (all against real deployed AWS resources)
- [x] Coverage target met (n/a — infra code)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-002*
