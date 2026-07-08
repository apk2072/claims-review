---
id: pipeline-orchestration
title: Step Functions pipeline orchestration skeleton
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [aws-foundation-infra]
created: 2026-07-05T00:00:00Z
---

# Work Item: Step Functions pipeline orchestration skeleton

## Description

CDK-defined Step Functions state machine that will wire together the bronze/silver/gold Lambda steps (implemented in later work items) into one document-processing workflow, triggered by the S3 event notification from work item 2. Build the state machine shape and wiring now with placeholder/no-op Lambda targets, so later work items only need to implement each Lambda's logic.

## Acceptance Criteria

- [ ] Step Functions state machine defined in CDK with states for: parse (bronze) → classify+extract (silver) → confidence-blend+route (gold)
- [ ] S3 event notification (from work item 2) triggers the state machine (directly or via EventBridge) on new object creation
- [ ] Each state currently invokes a placeholder Lambda that just logs its input and passes through, proving the wiring works end-to-end
- [ ] Failure handling: a failed state doesn't crash the whole execution — catches route to a `failed` terminal state per document
- [ ] One manual test: drop a fixture file in S3, confirm the state machine executes all states successfully in the Step Functions console/CLI

## Technical Notes

Keep this deliberately thin — the goal is proving the orchestration shape works before investing in the real Bedrock/Textract logic. This also gives an early, demoable "something is happening in AWS" milestone.

## Dependencies

- aws-foundation-infra
