---
run: run-claims-review-002
work_item: aws-foundation-infra
intent: claims-review-platform
generated: 2026-07-07T05:43:42.558Z
mode: validate
---

# Implementation Walkthrough: AWS foundation infrastructure (VPC, S3, IAM, Aurora cluster)

## Summary

Deployed the shared AWS foundation for the whole platform: a cost-conscious VPC, an encrypted S3 bucket for claim documents, and an Aurora Serverless v2 Postgres cluster with pgvector enabled and scale-to-zero capacity. Verified — against real deployed resources, not mocks — that pgvector installs, that a VPC-attached Lambda can actually reach Aurora across the security-group boundary, and that the whole stack survives a full `cdk destroy` + `cdk deploy` teardown/rebuild cycle.

## Structure Overview

`ClaimsReviewFoundationStack` now defines four logical groups of resources: networking (VPC, subnets, NAT), storage (S3 bucket), data (Aurora Serverless v2 cluster + its dedicated security group), and one temporary verification Lambda + its security group. Nothing else in the codebase depends on this stack yet — it exists purely as the foundation the next several work items (schema migrations, pipeline Lambdas, backend/agent Fargate services) will attach to.

## Architecture

### Pattern Used

Three-tier subnet isolation (public / private-with-egress / private-isolated) with the database confined to the innermost tier and no direct route to the internet — standard defense-in-depth network design.

### Layer Structure

```text
┌──────────────────────────────────────────┐
│  Public subnets (NAT Gateway, IGW)         │
├──────────────────────────────────────────┤
│  Private-with-egress (future Lambda/Fargate;│
│  currently just the one-off test Lambda)   │
├──────────────────────────────────────────┤
│  Isolated (Aurora Serverless v2 only,      │
│  no internet route)                        │
└──────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `infra/src/infra/test_connectivity_handler.py` | One-off Lambda handler proving the VPC→Aurora network path via a minimal Postgres `SSLRequest` probe (stdlib-only; no compiled DB driver, since Docker isn't available on this machine for asset bundling) |

### Modified

| File | Changes |
|------|---------|
| `infra/src/infra/foundation_stack.py` | Replaced the empty placeholder with real VPC, S3 bucket, Aurora Serverless v2 cluster, and the connectivity-test Lambda + scoped security groups |
| `infra/README.md` | Documented deployed resource details, cost estimate, and the teardown command |

## Key Implementation Details

### 1. Security-group-to-security-group ingress, not blanket VPC CIDR

The approved design didn't fully specify this, but during implementation the Aurora security group was scoped to accept ingress only from the specific security groups of resources that need access (starting with the test Lambda's SG), rather than a blanket "anything in the VPC" rule. Each future compute resource (pipeline Lambdas, backend/agent Fargate tasks) will add its own explicit ingress rule when it's created — mirrors the same incremental, least-privilege pattern the design doc already established for IAM roles.

### 2. pgvector verified via RDS Data API, not a direct psycopg connection

The original plan assumed a Lambda with `psycopg` installed could both check network connectivity and run the pgvector `CREATE EXTENSION` statement. No Docker was available on this machine to bundle a compiled driver into a Lambda package (CDK's `PythonFunction`/Docker-based bundling needs it), so verification was split: a dependency-free Lambda proves the network path (TCP connect + Postgres `SSLRequest`/reply exchange), and `enable_data_api=True` on the cluster lets the pgvector check run via `aws rds-data execute-statement` — no VPC attachment or driver needed for that half at all.

### 3. Scale-to-zero cold start is real and expected

The first `rds-data execute-statement` call after the cluster came up (and again after the destroy/rebuild cycle) returned `DatabaseResumingException` — Aurora Serverless v2 resuming from 0 ACU. Retrying ~15s later succeeded both times. This is documented in `infra/README.md` as an expected tradeoff, not a bug.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| NAT strategy | Single NAT Gateway | Cheaper than 5+ VPC interface endpoints at this scale; cost controlled via `cdk destroy` between sessions instead |
| Aurora capacity | min 0 / max 2 ACU | Scale-to-zero for near-$0 idle cost; confirmed ~15-30s cold start on resume, twice |
| IAM approach | No pre-created shared roles | CDK's per-resource auto-generated execution role + incremental `grant*()` calls IS the least-privilege pattern, not a shortcut around it |
| Aurora security group ingress | SG-to-SG rules per consumer, not blanket VPC CIDR | Refined during implementation for tighter least-privilege than the original design draft |
| pgvector verification method | RDS Data API instead of psycopg-in-Lambda | No Docker available on this machine for compiled-dependency bundling |

## Deviations from Plan

Two implementation-time adjustments from the approved plan, both documented above and consistent with the design's underlying intent (verify connectivity, verify pgvector, least-privilege networking) rather than changing scope, cost, or architecture:

1. **Security group ingress scoped per-consumer instead of VPC-CIDR-wide** — a security tightening, not a scope change.
2. **Connectivity verification split into a stdlib-only TCP/SSLRequest check (Lambda) + RDS Data API (pgvector)** instead of a single psycopg-based Lambda — forced by the lack of Docker on this machine for CDK asset bundling; achieves the same verification goals.

Additionally, the plan's temporary test Lambda was **kept deployed** (not removed) as a documented reusable debug tool for re-checking VPC/security-group connectivity later, per the plan's own "left as a documented debug tool" option.

## Dependencies Added

No new Python/npm dependencies — this work item only used `aws-cdk-lib` constructs already declared in `infra/pyproject.toml` from the `project-scaffold` work item.

## How to Verify

1. **Stack is deployed and healthy**

   ```bash
   aws cloudformation describe-stacks --stack-name ClaimsReviewFoundation --region us-east-1 --query "Stacks[0].StackStatus"
   ```

   Expected: `"CREATE_COMPLETE"` or `"UPDATE_COMPLETE"`

2. **pgvector is installed**

   ```bash
   CLUSTER_ARN=$(aws rds describe-db-clusters --region us-east-1 --query "DBClusters[?contains(DBClusterIdentifier, 'auroracluster')].DBClusterArn" --output text)
   SECRET_ARN=<AuroraSecretArn from stack outputs>
   aws rds-data execute-statement --region us-east-1 --resource-arn "$CLUSTER_ARN" --secret-arn "$SECRET_ARN" \
     --database claims_review --sql "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
   ```

   Expected: `"stringValue": "0.8.1"` (retry once if `DatabaseResumingException` — cold start)

3. **VPC connectivity works**

   ```bash
   aws lambda invoke --region us-east-1 --function-name <ConnectivityTestFunctionName from outputs> /tmp/out.json && cat /tmp/out.json
   ```

   Expected: `{"reachable": true, ..., "postgres_ssl_reply": "S"}`

4. **Teardown works**

   ```bash
   cd infra && JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk destroy --force
   ```

   Expected: all resources deleted, stack removed from CloudFormation

## Test Coverage

- Tests added: 0 (infrastructure-definition code; verified via real deployment per `testing-standards.md`)
- Coverage: n/a
- Status: all manual verification passing, including a full destroy/rebuild cycle (see `test-report.md`)

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing (real AWS resources)
- [x] No critical issues
- [x] Documentation updated (`infra/README.md`, design doc)
- [x] Developer notes captured

## Developer Notes

- **EC2 `SecurityGroup` descriptions must be plain ASCII** — em-dashes and other non-ASCII punctuation will fail `CREATE_FAILED` at deploy time, not at `cdk synth`. Worth grepping for non-ASCII characters in any new `description=` string before deploying.
- **Postgres doesn't send an unsolicited banner on TCP connect** — a naive `sock.recv()` right after connecting will hang until timeout even on a perfectly healthy connection. If you need to prove "something Postgres-shaped is listening" without a real driver, send a minimal `SSLRequest` (8 bytes: length=8, code=80877103) and read the 1-byte `S`/`N` reply.
- **RDS Data API (`enable_data_api=True`) is a good escape hatch** for one-off SQL checks against a VPC-isolated Aurora cluster when you don't want to stand up a bastion, VPN, or Docker-bundled Lambda driver just to run a single statement.
- A CloudFormation stack stuck in `ROLLBACK_COMPLETE` **cannot be updated** — it must be deleted (`aws cloudformation delete-stack` + `wait stack-delete-complete`, or `cdk destroy`) before the next `cdk deploy` will succeed.
- The `ConnectivityTestFunction` Lambda is intentionally left deployed as a reusable debug tool — re-invoke it any time VPC/security-group connectivity is suspected of being broken in a later work item.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-002*
