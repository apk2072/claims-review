---
run: run-claims-review-001
work_item: project-scaffold
intent: claims-review-platform
mode: autopilot
checkpoint: none
approved_at: n/a (autopilot)
---

# Implementation Plan: Project scaffold and toolchain setup

## Approach

Set up a `uv` workspace at the repo root with one member per Python component (`pipeline`, `backend`, `agent`, `eval`, `common`, `infra`), each with its own minimal `pyproject.toml`. `common/` holds shared models/config importable by the others. `infra/` is a minimal hand-built AWS CDK (Python) app with zero real resources yet — just an empty placeholder stack so `cdk synth` succeeds and `cdk bootstrap` status can be checked. `frontend/` is a Vite + React + TypeScript scaffold via `npm create vite`. Root `ruff.toml` applies lint/format config across all Python components. Each component gets a one-paragraph README. No AWS resources are created in this work item — confirm AWS CLI identity and CDK bootstrap status only.

## Files to Create

| File | Purpose |
|------|---------|
| `pyproject.toml` (root) | uv workspace definition listing all Python members |
| `ruff.toml` | Shared lint/format config for all Python components |
| `common/pyproject.toml`, `common/src/common/__init__.py` | Shared package (models/config) importable by other components |
| `pipeline/pyproject.toml`, `pipeline/README.md` | Bronze/Silver/Gold pipeline component |
| `backend/pyproject.toml`, `backend/README.md` | FastAPI reviewer backend component |
| `agent/pyproject.toml`, `agent/README.md` | LangGraph assistant agent component |
| `eval/pyproject.toml`, `eval/README.md` | Eval curation + GEPA prompt optimization component |
| `infra/pyproject.toml`, `infra/app.py`, `infra/cdk.json`, `infra/README.md` | CDK app skeleton, one empty placeholder stack |
| `frontend/` (Vite scaffold) | React + TypeScript reviewer web app scaffold |
| `README.md` (root) | Project overview, links to `.specs-fire/` docs and per-component READMEs |
| `.gitignore` | Python/Node/CDK/uv ignores |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | |

## Tests

| Test File | Coverage |
|-----------|----------|
| (manual verification) | `uv run python -c "print('ok')"` in each Python component; `npm run build` in frontend; `cdk synth` in infra |

## Technical Details

- `uv` workspace root `pyproject.toml` uses `[tool.uv.workspace] members = ["common", "pipeline", "backend", "agent", "eval", "infra"]`.
- Each Python component's `pyproject.toml` declares `common` as a workspace dependency where it needs shared models (pipeline, backend, agent).
- `infra/app.py` instantiates one empty `ClaimsReviewFoundationStack(app, "ClaimsReviewFoundation")` with no resources — real resources land in work item `aws-foundation-infra`.
- This work item also checks (does not fix) AWS CDK bootstrap status in the target account/region (`us-east-1`) via `aws sts get-caller-identity` and `cdk bootstrap` dry indicators, surfacing findings in `infra/README.md` for the next work item to act on.

---
*Autopilot mode — plan saved for visibility, no approval checkpoint.*
