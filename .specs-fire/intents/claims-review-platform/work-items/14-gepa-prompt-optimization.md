---
id: gepa-prompt-optimization
title: GEPA prompt optimization and promotion gate
intent: claims-review-platform
complexity: high
mode: validate
status: pending
depends_on: [eval-curation-scoring]
created: 2026-07-05T00:00:00Z
---

# Work Item: GEPA prompt optimization and promotion gate

## Description

Implement the capstone learning-loop piece: GEPA-based challenger prompt generation from the curated eval dataset (60/40 train/holdout split), and a promotion gate enforcing hard floors (safety: zero regression, correctness: max -0.01 regression) plus a paired bootstrap confidence-interval check on the composite score delta, with a minimum of 20 paired examples. Promoted prompts publish to the MLflow Prompt Registry and the agent picks up the new champion prompt.

## Acceptance Criteria

- [ ] GEPA (or an equivalent reflective prompt-optimization loop, implemented directly if the GEPA library doesn't integrate cleanly) generates at least one challenger prompt from real curated failures
- [ ] Promotion gate implemented as a pure, unit-tested function: safety floor, correctness floor, minimum paired-examples check, bootstrap CI check
- [ ] Held-out split never seen by GEPA during generation — verified by construction (test asserts holdout indices excluded from training calls)
- [ ] Run once for real end-to-end: curated dataset → challenger generated → promotion gate evaluated → (if passed) new champion prompt published to MLflow Prompt Registry
- [ ] Agent service (work item 11) reloads/uses the champion prompt from the registry on next conversation

## Technical Notes

Highest conceptual complexity in the project and the best "I actually built the hard part" interview talking point — hence `validate` mode. If GEPA's public library proves too heavy to integrate in the time available, implementing the reflect-generate-select loop directly in Python against Bedrock is an acceptable substitute — the promotion-gate statistics matter more than using the exact GEPA package.

## Dependencies

- eval-curation-scoring
