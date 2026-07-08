---
run: run-claims-review-001
work_item: project-scaffold
intent: claims-review-platform
generated: 2026-07-06T03:16:28.859Z
mode: autopilot
---

# Implementation Walkthrough: Project scaffold and toolchain setup

## Summary

Stood up the full repo skeleton for the claims-review platform: a `uv` workspace with six Python members (`common`, `pipeline`, `backend`, `agent`, `eval`/`claims_eval`, `infra`), a Vite + React + TypeScript frontend, and a minimal AWS CDK app with one empty placeholder stack. Confirmed the real toolchain end-to-end — AWS identity, CDK bootstrap status, `cdk synth`, `ruff` lint/format, and per-component imports — all before any real AWS resources exist.

## Structure Overview

The repo is a single `uv` workspace rooted at `pyproject.toml`, with each component (`pipeline/`, `backend/`, `agent/`, `eval/`, `common/`, `infra/`) as an independent workspace member sharing one lockfile and one `.venv`. `common/` holds shared models/config that `pipeline`, `backend`, and `agent` depend on via `[tool.uv.sources] common = { workspace = true }`. `infra/` is a separate Python package (CDK app) that does not depend on `common` since infrastructure code has no business-logic overlap with the application components. `frontend/` is a standalone Node/npm project, not part of the uv workspace.

## Architecture

### Pattern Used

Monorepo with independently-runnable components sharing a workspace-level dependency resolver (`uv`). This mirrors the medallion-pipeline / operational-app / agent / eval-loop layering from `system-architecture.md` at the directory level, before any of those layers have real logic.

### Layer Structure

```text
┌─────────────────────────────────────────────┐
│  frontend/  (React + Vite, standalone npm)   │
├─────────────────────────────────────────────┤
│  backend/   agent/   pipeline/   eval/       │  ← uv workspace members
├─────────────────────────────────────────────┤
│  common/    (shared models/config)           │  ← uv workspace member
├─────────────────────────────────────────────┤
│  infra/     (CDK app, independent package)   │  ← uv workspace member
└─────────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `pyproject.toml` | uv workspace root config (members + dev dependency group) |
| `ruff.toml` | Shared lint/format config for all Python components |
| `.gitignore` | Repo-wide ignores (venv, node_modules, cdk.out, env files) |
| `README.md` | Project overview, links to `.specs-fire/` docs |
| `common/pyproject.toml`, `common/src/common/__init__.py` | Shared package skeleton |
| `pipeline/pyproject.toml`, `pipeline/src/pipeline/__init__.py`, `pipeline/README.md` | Pipeline component skeleton |
| `backend/pyproject.toml`, `backend/src/backend/__init__.py`, `backend/README.md` | Backend component skeleton |
| `agent/pyproject.toml`, `agent/src/agent/__init__.py`, `agent/README.md` | Agent component skeleton |
| `eval/pyproject.toml`, `eval/src/claims_eval/__init__.py`, `eval/README.md` | Eval component skeleton (package name `claims_eval` to avoid shadowing Python's builtin `eval`) |
| `infra/pyproject.toml`, `infra/app.py`, `infra/cdk.json`, `infra/src/infra/__init__.py`, `infra/src/infra/foundation_stack.py`, `infra/README.md` | CDK app skeleton with one empty placeholder stack |
| `frontend/` | Vite-generated React + TypeScript scaffold (unmodified from template) |

### Modified

(none — this was a pure scaffolding run, nothing pre-existing to modify)

## Key Implementation Details

### 1. uv workspace instead of per-component virtualenvs

Chose a single `uv` workspace (`[tool.uv.workspace] members = [...]`) over independent virtualenvs per component so `common` can be a real local dependency (`{ workspace = true }`) rather than a copy-pasted or path-hacked import, and so there's one lockfile to reason about.

### 2. `eval/` package named `claims_eval`

The directory is `eval/` (per `system-architecture.md`), but the importable Python module is `claims_eval` — importing a module literally named `eval` would shadow Python's builtin `eval()` function everywhere it's imported.

### 3. CDK app is Python but doesn't depend on `common`

`infra/` is a workspace member for consistency (one lockfile, one `uv sync --all-packages`), but intentionally has no dependency on `common` — infrastructure-definition code and application business logic don't share models.

### 4. Toolchain verification done for real, not assumed

Rather than just scaffolding files, actually ran: `uv sync --all-packages`, all workspace imports, `uv run --package {x} python -c "print('ok')"` for each component, `ruff check`/`ruff format --check`, `cdk synth`, `npm run build` for the frontend, `aws sts get-caller-identity`, and a check of the `CDKToolkit` CloudFormation stack to confirm bootstrap status — all before the next work item touches real AWS resources.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Python monorepo tool | `uv` workspace | Single lockfile/venv across 6 Python components, native local-package support via `tool.uv.sources` |
| Eval package name | `claims_eval` (dir stays `eval/`) | Avoid shadowing Python's builtin `eval()` |
| CDK app dependency on `common` | None | Infra code has no overlap with app business models |
| Dev tooling | `ruff` + `mypy` + `pytest` + `pytest-asyncio` + `moto` as a `uv` dev dependency group at the workspace root | Shared across all components, installed once |

## Deviations from Plan

None — matches the plan in `plan.md` exactly. One trivial addition not explicitly listed in the plan: added a `dependency-groups.dev` section to the root `pyproject.toml` for `ruff`/`mypy`/`pytest`/`pytest-asyncio`/`moto`, since the plan's acceptance criteria required `ruff` to actually run, which needed it installed somewhere.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `moto` (dev group) | Lint/type-check/test tooling per `testing-standards.md` / `coding-standards.md` |
| `aws-cdk-lib`, `constructs` (infra) | CDK app dependencies |
| `pydantic` (common) | Shared model validation |
| `boto3` (pipeline) | AWS SDK for future Textract/Bedrock calls |
| `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pgvector` (backend) | Reviewer API + Aurora access, declared now for the next work items |
| `langgraph`, `langchain-aws`, `mlflow` (agent) | Agent orchestration + Bedrock + tracing, declared now for later work items |
| `mlflow`, `boto3` (eval) | Eval curation + Bedrock LLM-as-judge, declared now for later work items |
| `aws-cdk` (npm, global) | CDK CLI (not previously installed on this machine) |
| `yaml` (npm, project-local) | Required by FIRE's own run-execute scripts (`init-run.cjs` etc.) |

## How to Verify

1. **Workspace installs and all packages import**

   ```bash
   uv sync --all-packages
   JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 uv run python -c "import fastapi, aws_cdk, langgraph, mlflow, common, pipeline, backend, agent, claims_eval, infra; print('all workspace imports ok')"
   ```

   Expected: `all workspace imports ok`

2. **Lint/format clean**

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   ```

   Expected: `All checks passed!` and `N files already formatted`

3. **CDK synthesizes**

   ```bash
   cd infra && JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk synth
   ```

   Expected: CloudFormation template for `ClaimsReviewFoundation` with no resources besides `CDKMetadata`

4. **Frontend builds**

   ```bash
   cd frontend && npm run build
   ```

   Expected: Vite build succeeds, `dist/` produced

## Test Coverage

- Tests added: 0 (no application logic exists yet — intentional for a scaffolding-only work item)
- Coverage: n/a
- Status: all manual verification checks passing (see `test-report.md`)

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing (manual verification)
- [x] No critical issues
- [x] Documentation updated (per-component READMEs + root README)
- [x] Developer notes captured

## Developer Notes

- CDK's jsii runtime warns loudly about untested Node.js versions (this machine runs Node 25; jsii officially supports 20/22/24). It's cosmetic — set `JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1` in your shell profile if it gets annoying across future CDK commands.
- `uv sync --all-packages` is required, not just `uv sync` — plain `uv sync` at the workspace root only installs the root project's own (empty) dependency set, not the members'. Easy to forget and get confusing `ModuleNotFoundError`s.
- If you add a new `__init__.py` to a workspace member after it's already been synced once, you may need `uv sync --all-packages --reinstall-package <name>` — otherwise uv can serve a stale cached wheel built before the file existed (hit this exact issue with `claims_eval`, `pipeline`, `backend`, `agent` in this run).
- CDK bootstrap was already done in this AWS account/region from prior work — no `cdk bootstrap` needed before the next work item's real deploy.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-claims-review-001*
