---
id: synthetic-claims-fixtures
title: Synthetic claims document fixtures
intent: claims-review-platform
complexity: low
mode: autopilot
status: pending
depends_on: []
created: 2026-07-05T00:00:00Z
---

# Work Item: Synthetic claims document fixtures

## Description

Produce a small, fixed set of synthetic (never-real-PHI) claim documents covering the scenarios the pipeline needs to demonstrate: a clean high-confidence claim form, a blurry/low-quality scan, a form missing required fields, and a document that isn't a claim form at all (to exercise classification). Generated as simple PDFs (can be created programmatically, e.g. with `reportlab` or similar, using obviously fake patient/claim data).

## Acceptance Criteria

- [ ] 4+ synthetic PDF/image fixtures saved under `pipeline/tests/fixtures/sample_claims/`
- [ ] Each fixture uses clearly fake identifiers (e.g. "Jane Test Doe", fabricated claim/member IDs) — no real-sounding SSNs/MRNs
- [ ] A short `fixtures/README.md` documents what each fixture is meant to exercise (clean/blurry/missing-field/wrong-type)
- [ ] Fixtures are small enough to commit to git directly (no LFS needed)

## Technical Notes

Can be built independently of any AWS infrastructure — pure local generation. Keep the generation script (if any) so more fixtures can be produced later if a specific pipeline edge case needs a new sample.

## Dependencies

(none)
