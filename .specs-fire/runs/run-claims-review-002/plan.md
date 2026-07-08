---
run: run-claims-review-002
work_item: aws-foundation-infra
intent: claims-review-platform
mode: validate
checkpoint: plan
approved_at: pending
---

# Implementation Plan: AWS foundation infrastructure (VPC, S3, IAM, Aurora cluster)

Based on approved design document: `.specs-fire/intents/claims-review-platform/work-items/aws-foundation-infra-design.md`

## Approach

Replace the empty `ClaimsReviewFoundationStack` placeholder with real CDK constructs: a VPC (2 AZs, public + private-with-NAT + isolated subnet groups, 1 NAT Gateway), an encrypted S3 bucket with EventBridge notifications enabled, and an Aurora Serverless v2 Postgres cluster (16.x, min 0 / max 2 ACU, Secrets Manager credentials) in the isolated subnets. Deploy via `cdk deploy`, then run one-off verification: confirm pgvector installs, confirm a test Lambda in the VPC can reach Aurora, record cost estimate in `infra/README.md`, then run `cdk destroy` followed by `cdk deploy` once to prove the teardown/rebuild cycle.

## Implementation Checklist (from design doc)

- [ ] Define VPC (2 AZs; public, NAT-routed private, and isolated subnet groups; 1 NAT Gateway)
- [ ] Define S3 bucket (SSE-S3, Block Public Access, EventBridge notifications enabled, versioning off)
- [ ] Define Aurora Serverless v2 Postgres cluster (isolated subnet group, min 0 / max 2 ACU, Secrets Manager credentials, 16.x engine)
- [ ] `cdk deploy`
- [ ] Confirm pgvector extension via one-off connection
- [ ] Confirm VPC connectivity path (temporary test Lambda) reaches Aurora
- [ ] Record cost estimate + teardown command in infra/README.md
- [ ] Run `cdk destroy` once, then `cdk deploy` again, to prove the teardown/rebuild cycle works

## Files to Create

| File | Purpose |
|------|---------|
| `infra/src/infra/test_connectivity_handler.py` | Temporary Lambda handler used only to verify VPC→Aurora connectivity; removed (or left as a documented debug tool) after verification |

## Files to Modify

| File | Changes |
|------|---------|
| `infra/src/infra/foundation_stack.py` | Add VPC, S3 bucket, Aurora Serverless v2 cluster, temporary test Lambda + security group rules |
| `infra/README.md` | Add cost estimate, VPC/Aurora/S3 details, teardown command |

## Tests

| Test File | Coverage |
|-----------|----------|
| (manual verification) | `cdk deploy`, pgvector `CREATE EXTENSION` check, test Lambda invoke reaching Aurora, `cdk destroy` + re-`cdk deploy` cycle |

## Technical Details

- VPC: `ec2.Vpc` with `max_azs=2`, three subnet groups (`PUBLIC`, `PRIVATE_WITH_EGRESS` for future Lambda/Fargate, `PRIVATE_ISOLATED` for Aurora), `nat_gateways=1`.
- S3: `s3.Bucket` with `encryption=S3_MANAGED`, `block_public_access=BLOCK_ALL`, `event_bridge_enabled=True`, `versioned=False`, `removal_policy=DESTROY` + `auto_delete_objects=True` (acceptable for a learning project so `cdk destroy` fully tears down; would be `RETAIN` in a real production system).
- Aurora: `rds.DatabaseCluster` with `engine=AURORA_POSTGRESQL` (latest 16.x available in CDK), `serverless_v2_min_capacity=0`, `serverless_v2_max_capacity=2`, `vpc_subnets` pinned to the isolated subnet group, `credentials=rds.Credentials.from_generated_secret(...)`, `writer=rds.ClusterInstance.serverlessV2(...)`.
- Temporary test Lambda: minimal Python handler that opens a psycopg connection to Aurora (using Secrets Manager credentials) and runs `SELECT 1` plus `CREATE EXTENSION IF NOT EXISTS vector;`, deployed into the private-with-egress subnet with a security group allowing outbound to Aurora's security group on 5432. Invoked once manually via `aws lambda invoke`, output inspected, then either removed in a follow-up `cdk deploy` or left in place with a comment marking it as a debug tool (decide at implementation time based on how clean vs. how fast).

---
Checkpoint 2 of Validate mode.

Approve implementation plan? [Y/n/edit]
