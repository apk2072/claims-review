---
id: silver-classify-extract
title: Silver layer — Bedrock classify, extract, and composite confidence
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [bronze-textract-parse]
created: 2026-07-05T00:00:00Z
---

# Work Item: Silver layer — Bedrock classify, extract, and composite confidence

## Description

Implement the "classify+extract" Lambda: calls Amazon Bedrock (Claude) twice — once to classify document type, once to extract structured field/value pairs with the model asked to self-report per-field confidence — then computes the composite confidence score (60% extract confidence mean, 20% parse confidence mean from bronze, 20% completeness) and persists silver-layer results to Aurora.

## Acceptance Criteria

- [ ] Lambda replaces the silver placeholder from work item 5
- [ ] Classification prompt returns a document type label for each of the 4 fixtures (including correctly flagging the "wrong document type" fixture)
- [ ] Extraction prompt returns field/value pairs plus a confidence float per field, using structured output (Pydantic-validated JSON from the model)
- [ ] `compute_composite_score()` implemented per the 60/20/20 weighting, unit-tested directly (no AWS calls needed) including the edge case where per-field confidence is unavailable and the parse-confidence weight coalesces onto extract confidence
- [ ] Unit tests with mocked Bedrock responses (captured fixture JSON) cover: high-confidence doc, low-confidence/missing-field doc

## Technical Notes

This is the direct analog of `ai_classify` + `ai_extract`. The composite score formula is a named, testable pure function (`compute_composite_score`) per `coding-standards.md`'s anti-pattern note about not scattering thresholds — keep the 60/20/20 weights as named constants in one config location.

## Dependencies

- bronze-textract-parse
