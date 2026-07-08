---
id: demo-and-teardown
title: End-to-end demo run, teardown script, and interview walkthrough notes
intent: claims-review-platform
complexity: low
mode: autopilot
status: pending
depends_on: [gold-verdict-routing, reviewer-frontend-app, gepa-prompt-optimization]
created: 2026-07-05T00:00:00Z
---

# Work Item: End-to-end demo run, teardown script, and interview walkthrough notes

## Description

Run the full system once against all synthetic fixtures end-to-end, capture screenshots/recordings of the reviewer app and agent chat, write a `cdk destroy`-based teardown script (or documented sequence) to stop cost accrual between practice sessions, and write a short walkthrough doc mapping each AWS component back to its Databricks analog for interview reference.

## Acceptance Criteria

- [ ] Full pipeline run recorded: fixture upload → pipeline processing → reviewer queue → verdict submission → (if built) agent chat → (if built) eval/promotion cycle
- [ ] Teardown script/runbook stops or destroys costly resources (Fargate services, Aurora if fully done, NAT gateway) with a clear "how to bring it back up" note
- [ ] `INTERVIEW_NOTES.md` at repo root: one paragraph per component pairing it with its Databricks analog and the key design decision behind it
- [ ] All work items actually completed are listed with their current status; anything not completed by the deadline is clearly marked as "designed, not built" with a one-line explanation of what would come next

## Technical Notes

This item runs regardless of how far the stretch items (11-14) got — even a partial build should end with a clear, honest map of what's real vs. what's designed-only, since that distinction itself is a legitimate interview answer.

## Dependencies

- gold-verdict-routing
- reviewer-frontend-app
- gepa-prompt-optimization
