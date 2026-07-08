---
work_item: aws-foundation-infra
intent: claims-review-platform
created: 2026-07-06T00:00:00Z
mode: validate
checkpoint_1: approved
---

# Design: AWS foundation infrastructure (VPC, S3, IAM, Aurora cluster)

## Summary

CDK stack provisioning the shared foundation every other component depends on: a cost-conscious VPC, an S3 bucket for claim documents, an Aurora Serverless v2 Postgres cluster (pgvector-enabled, scale-to-zero), and an IAM strategy for later Lambda/Fargate services.

## Scope

**In Scope:**
- VPC (2 AZs, public/private/isolated subnets, 1 NAT Gateway)
- S3 bucket for claim documents (encrypted, EventBridge notifications enabled)
- Aurora Serverless v2 Postgres cluster (pgvector-enabled, scale-to-zero)
- IAM approach documentation (no pre-created shared roles)
- Cost estimate and teardown verification

**Out of Scope:**
- Lambda/Fargate resources
- Step Functions state machine
- Database schema/tables (separate work item)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| NAT strategy | Single NAT Gateway | Simplest, best-understood pattern; a VPC-endpoint-only setup would need 5+ interface endpoints (~$7/mo each) which costs more than one NAT Gateway (~$32-38/mo) at this scale. Cost controlled via `cdk destroy` between sessions instead. |
| Aurora topology | Single instance, single-AZ, no reader | No HA/failover need for a personal learning project; halves always-on cost vs. multi-AZ |
| Aurora Serverless v2 capacity | min 0 ACU (scale-to-zero), max 2 ACU | Near-$0 compute cost when idle; 2 ACU max is enough for pgvector + demo-scale traffic. Tradeoff: ~15s+ cold-start on first query after idle. |
| Engine version | Aurora PostgreSQL 16.x (latest CDK-supported minor) | pgvector supported from 15.3+/16.1+; matches tech-stack.md |
| S3 bucket config | SSE-S3 encryption, Block Public Access on, versioning off, EventBridge notifications enabled | Encryption-at-rest good practice; EventBridge notifications mean the bucket resource never needs to be touched again when pipeline-orchestration adds a rule later |
| IAM approach | No shared/pre-created IAM roles — each Lambda/Fargate task gets its own CDK-auto-generated execution role, permissions attached incrementally via `grant*()` calls | Deliberate deviation from the work item's literal wording; CDK's per-resource auto-generated + incrementally-granted roles IS the least-privilege pattern, avoids unused scaffolding roles |
| DB credentials | Auto-generated, stored in Secrets Manager (CDK default) | No credentials in code/env files, satisfies constitution's "no secrets in code" |

## Data Models Affected

None — no application tables in this item. Schema lands in `aurora-schema-migrations`.

## Technical Approach

### Architecture

```
                        VPC (10.0.0.0/16, 2 AZs)
  ┌─────────────────────────────────────────────────────────┐
  │  Public subnets (2)        Private subnets (2)            │
  │  ┌───────────────┐         ┌─────────────────────────┐    │
  │  │  NAT Gateway   │────────▶│  (future) Lambda/Fargate │    │
  │  └───────────────┘         └───────────┬─────────────┘    │
  │                                          │                 │
  │                              Isolated subnets (2)          │
  │                             ┌───────────▼─────────────┐    │
  │                             │  Aurora Serverless v2     │    │
  │                             │  Postgres 16.x + pgvector │    │
  │                             │  min 0 / max 2 ACU        │    │
  │                             └───────────────────────────┘   │
  └─────────────────────────────────────────────────────────┘

  S3 bucket (claim-documents) — SSE-S3, EventBridge notifications enabled
  (not in VPC — accessed over AWS public endpoints / future S3 gateway endpoint)
```

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `infra/src/infra/foundation_stack.py` | modify | Add VPC, S3 bucket, Aurora cluster constructs (replacing empty placeholder) |
| `infra/app.py` | modify | Pass through env/config if needed |
| `infra/README.md` | modify | Record cost estimate, bootstrap status, teardown command |

## Security Considerations

- **DB credentials**: Secrets Manager-managed, never in code
- **Network isolation**: Aurora has no public endpoint, isolated subnet with no internet route
- **Encryption at rest**: S3 SSE-S3 and Aurora storage encryption both enabled
- **PHI discipline**: no real data ever touches this — first item provisioning a real data store

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| NAT Gateway or Aurora left running accrues real cost between sessions | Medium | `cdk destroy` documented prominently in infra/README.md; full teardown runbook is work item 15 |
| Aurora scale-to-zero cold-start surprises a live demo | Low | Acceptable for practice; pre-warm with one query before a real demo |
| VPC/subnet misconfiguration blocks future Lambda/Fargate connectivity | Medium | Validate connectivity with a one-off test Lambda in this same work item |
| pgvector unsupported on chosen engine version | Low | Confirm via `CREATE EXTENSION IF NOT EXISTS vector;` immediately after deploy |

## Implementation Checklist

- [ ] Define VPC (2 AZs; public, NAT-routed private, and isolated subnet groups; 1 NAT Gateway)
- [ ] Define S3 bucket (SSE-S3, Block Public Access, EventBridge notifications enabled, versioning off)
- [ ] Define Aurora Serverless v2 Postgres cluster (isolated subnet group, min 0 / max 2 ACU, Secrets Manager credentials, 16.x engine)
- [ ] `cdk deploy`
- [ ] Confirm pgvector extension via one-off connection
- [ ] Confirm VPC connectivity path (temporary test Lambda) reaches Aurora
- [ ] Record cost estimate + teardown command in infra/README.md
- [ ] Run `cdk destroy` once, then `cdk deploy` again, to prove the teardown/rebuild cycle works

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-07-06T00:00:00Z*
