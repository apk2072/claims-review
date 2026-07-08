---
id: gold-verdict-routing
title: Gold layer — auto-verdict routing
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [silver-classify-extract]
created: 2026-07-05T00:00:00Z
---

# Work Item: Gold layer — auto-verdict routing

## Description

Implement the "route" Lambda: reads the composite confidence score from the silver layer, applies the 0.92 auto-verdict threshold (configurable), and writes the final gold-layer record to Aurora's `extractions` table with `is_automated` set appropriately. Documents above threshold are marked auto-approved; documents at or below threshold are queued for human review.

## Acceptance Criteria

- [ ] Lambda replaces the gold placeholder from work item 5
- [ ] Threshold read from an environment variable / config (not hardcoded), defaulting to 0.92
- [ ] `route_verdict()` pure function unit-tested on both sides of the boundary (0.93 → auto-approved, 0.91 → queued, exactly 0.92 → documented behavior either way)
- [ ] End-to-end manual test: all 4 synthetic fixtures flow S3 → bronze → silver → gold and land in Aurora with correct `is_automated` flags (clean doc auto-approved, blurry/missing-field docs queued)
- [ ] Gold-layer Aurora row includes confidence scores, classification, extracted fields, and routing decision — everything the reviewer app needs to render

## Technical Notes

This closes out the full pipeline — after this item, dropping a document in S3 should produce a fully processed, correctly-routed Aurora row with no human involvement yet. Good checkpoint to demo before starting the reviewer app.

## Dependencies

- silver-classify-extract
