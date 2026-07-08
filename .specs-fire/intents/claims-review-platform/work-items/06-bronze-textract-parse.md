---
id: bronze-textract-parse
title: Bronze layer — Textract document parsing
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [aws-foundation-infra, aurora-schema-migrations, synthetic-claims-fixtures, pipeline-orchestration]
created: 2026-07-05T00:00:00Z
---

# Work Item: Bronze layer — Textract document parsing

## Description

Implement the real "parse" Lambda in the Step Functions pipeline: calls Amazon Textract `AnalyzeDocument` (FORMS feature) on the S3 object, extracts per-element bounding boxes and confidence scores, and writes the raw parse result (as the bronze-layer record) to Aurora's `claims` table (or a bronze-specific table/column) keyed by document ID.

## Acceptance Criteria

- [ ] Lambda replaces the bronze placeholder from work item 5
- [ ] Successfully parses all 4 synthetic fixtures from work item 4, including the deliberately blurry one (lower confidence expected, not a crash)
- [ ] Per-element confidence scores and bounding boxes persisted (JSON column or normalized table — pick one and document why in the PR/commit)
- [ ] Retries configured for transient Textract errors (boto3 retry config), permanent failures route the document to a `failed` state rather than crashing the state machine
- [ ] Unit tests with `moto`-mocked Textract responses (captured fixture JSON) cover: clean doc, low-confidence doc, Textract error path

## Technical Notes

This is the direct analog of `ai_parse_document` from the reference architecture — worth being able to explain the mapping explicitly (Textract's bounding-box + confidence output vs. Databricks' AI Function).

## Dependencies

- aws-foundation-infra
- aurora-schema-migrations
- synthetic-claims-fixtures
- pipeline-orchestration
