---
id: aws-foundation-infra
title: AWS foundation infrastructure (VPC, S3, IAM, Aurora cluster)
intent: claims-review-platform
complexity: high
mode: validate
status: pending
depends_on: [project-scaffold]
created: 2026-07-05T00:00:00Z
---

# Work Item: AWS foundation infrastructure (VPC, S3, IAM, Aurora cluster)

## Description

CDK stack(s) provisioning the shared foundation every other component depends on: a VPC (public + private subnets, one NAT gateway to control cost), the claims-documents S3 bucket with event notifications enabled, an Aurora Serverless v2 Postgres cluster (private subnet, pgvector extension enabled), and the baseline IAM roles/policies used by Lambda and Fargate tasks later.

## Acceptance Criteria

- [ ] `cdk deploy` successfully provisions VPC, S3 bucket, Aurora Serverless v2 cluster (min/max ACU chosen for cost — scale to ~0.5 ACU min)
- [ ] S3 bucket has event notification configuration ready to target a Lambda (target added in a later work item)
- [ ] Aurora cluster reachable only from within the VPC (no public endpoint); pgvector extension confirmed installed via a one-off connection
- [ ] IAM roles for Lambda execution and ECS task execution/task roles created with least-privilege placeholders (to be scoped further as each service is added)
- [ ] A documented, one-command teardown path exists (`cdk destroy`) and is tested once
- [ ] Approximate monthly cost of always-on pieces (NAT gateway, Aurora minimum ACU) written down in `infra/README.md` so cost stays visible

## Technical Notes

This is the highest-risk/highest-blast-radius item (VPC + networking + database engine choices are hard to change later) — hence `validate` mode with a design doc pass before implementation. Key decisions to nail down in the design doc: single-AZ vs multi-AZ Aurora (single-AZ acceptable for this learning project to save cost), NAT gateway vs NAT instance vs VPC endpoints only, Aurora Serverless v2 min ACU (favor lowest that still supports pgvector reliably).

## Dependencies

- project-scaffold
