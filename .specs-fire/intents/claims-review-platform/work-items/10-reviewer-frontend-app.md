---
id: reviewer-frontend-app
title: Reviewer frontend app (React)
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [reviewer-backend-api]
created: 2026-07-05T00:00:00Z
---

# Work Item: Reviewer frontend app (React)

## Description

React + Vite reviewer web app with three views: an overview dashboard (accuracy/performance/efficiency metrics from the backend), a reviewer queue (documents stratified by stage, side-by-side document view + extracted fields with approve/reject/correct actions), and a placeholder panel reserved for the assistant chat (implemented fully once work item 11 lands).

## Acceptance Criteria

- [ ] Dashboard view renders the three metric categories from `GET /dashboard/summary`
- [ ] Queue view lists claims by stage and lets a reviewer open one into a detail view
- [ ] Detail view shows the source document alongside extracted fields with per-field confidence, and lets the reviewer approve/reject/correct each field, calling `POST /claims/{id}/verdict`
- [ ] Assistant chat panel exists as a UI shell (visible, non-functional placeholder) so it's ready to wire up in work item 11
- [ ] Component tests (Vitest + RTL) cover the verdict-submission interaction
- [ ] Manually verified end-to-end against the running backend + real synthetic-fixture data using the preview tools

## Technical Notes

This is the point where the project becomes visually demoable — worth taking a screenshot/recording for interview talking points once this lands.

## Dependencies

- reviewer-backend-api
