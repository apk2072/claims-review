---
id: project-scaffold
title: Project scaffold and toolchain setup
intent: claims-review-platform
complexity: low
mode: autopilot
status: pending
depends_on: []
created: 2026-07-05T00:00:00Z
---

# Work Item: Project scaffold and toolchain setup

## Description

Create the top-level repo structure (`pipeline/`, `backend/`, `agent/`, `frontend/`, `infra/`, `eval/`) per `system-architecture.md`, with `uv`-managed Python projects for the Python components and an `npm`/Vite scaffold for the frontend. Each component gets a README stub describing its purpose and how to run/test it locally. CDK app skeleton created in `infra/` (empty stacks, no resources yet).

## Acceptance Criteria

- [ ] Directory structure matches `coding-standards.md`'s "Project Structure" section
- [ ] `pipeline/`, `backend/`, `agent/`, `eval/` each have a `pyproject.toml` (uv-managed) and pass `uv run python -c "print('ok')"`
- [ ] `frontend/` is a working Vite + React + TypeScript scaffold (`npm run dev` serves a blank page)
- [ ] `infra/` is a CDK app (`cdk synth` succeeds with zero stacks or one empty placeholder stack)
- [ ] Root `ruff.toml` and per-component lint configs exist
- [ ] Each component has a one-paragraph README

## Technical Notes

No AWS resources created yet — this is pure local scaffolding. Confirm AWS CLI default profile and CDK bootstrap status in this item too (`aws sts get-caller-identity`, `cdk bootstrap` if not already bootstrapped in the account/region).

## Dependencies

(none)
