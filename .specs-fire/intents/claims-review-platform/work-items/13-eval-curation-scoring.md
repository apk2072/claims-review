---
id: eval-curation-scoring
title: Eval dataset curation and weighted composite scoring
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [reviewer-backend-api, mlflow-tracing-setup]
created: 2026-07-05T00:00:00Z
---

# Work Item: Eval dataset curation and weighted composite scoring

## Description

Job (runnable manually or on a schedule) that curates a high-signal evaluation dataset from MLflow traces — including only traces tagged with `human_feedback`, traces failing inline scorers below threshold, or explicitly bookmarked traces — avoiding the "dump everything into eval" anti-pattern. Implements the weighted composite scorer (correctness 50%, safety 25%, relevance 12.5%, tool-call correctness 12.5%) using LLM-as-judge scoring via Bedrock.

## Acceptance Criteria

- [ ] Curation job queries MLflow traces and filters to the three inclusion criteria above
- [ ] Curated traces saved as an MLflow evaluation dataset
- [ ] Four scorers implemented (correctness, safety, relevance, tool-call correctness) with the documented weights, each independently unit-testable on a fixed trace fixture
- [ ] Run once for real against traces generated in work item 12, producing a non-trivial (not empty, not everything) curated dataset
- [ ] Composite score computation is a pure, unit-tested function separate from the LLM-as-judge calls

## Technical Notes

This is where the "closed loop" story becomes concrete — worth generating a handful of deliberately-corrected verdicts in the reviewer app first, so this job has real human-feedback traces to curate.

## Dependencies

- reviewer-backend-api
- mlflow-tracing-setup
