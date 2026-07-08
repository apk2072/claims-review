# Coding Standards

## Overview

Python-first project (pipeline, backend, agent, infra) with a TypeScript/React frontend. Standards favor readability and explicitness over cleverness — this is a learning project, and code should be easy to explain out loud in an interview.

## Code Formatting

**Tool**: `ruff format` (Python), `prettier` (frontend)
**Config**: `ruff.toml` at repo root; default Prettier config in `frontend/`
**Enforcement**: run manually before commit (`ruff format .`, `npm run format`); no pre-commit hook required for this solo project

### Key Settings

- **Line length**: 100 (Python), 80 (frontend/Prettier default)
- **Quote style**: double quotes (both Python and TS)

## Linting

**Tool**: `ruff` (Python), `eslint` (TypeScript/React)
**Base Config**: `ruff` default rule set + `E`, `F`, `I`, `UP`; ESLint `eslint:recommended` + `@typescript-eslint/recommended`
**Strictness**: warnings allowed locally, but fix before marking a work item complete

### Key Rules

- `I001` (import sorting) — enabled — keeps import blocks consistent across many small Lambda handlers
- `UP` (pyupgrade) — enabled — keep syntax on modern Python 3.12 idioms
- `no-unused-vars` (eslint) — error — catches dead state in React components early

## Naming Conventions

### Variables and Functions

| Element | Convention | Example |
|---------|------------|---------|
| Python variables/functions | snake_case | `confidence_score`, `compute_composite_score()` |
| Python classes | PascalCase | `ClaimDocument`, `ExtractionResult` |
| Python constants | UPPER_SNAKE_CASE | `AUTO_VERDICT_THRESHOLD` |
| TS/React variables/functions | camelCase | `reviewQueue`, `fetchClaims()` |
| React components | PascalCase | `ReviewerQueue`, `ClaimDetailPanel` |
| SQL tables/columns | snake_case | `claim_extractions`, `reviewer_verdict` |

### Files and Folders

- **Python modules**: snake_case (e.g., `confidence_scoring.py`)
- **React components**: PascalCase file matching component name (e.g., `ReviewerQueue.tsx`)
- **CDK stacks**: PascalCase class, snake_case file (e.g., `pipeline_stack.py` → `PipelineStack`)

## File Organization

### Project Structure

```
claims-review/
├── pipeline/          # Bronze/Silver/Gold document processing (Lambda + Step Functions)
│   ├── bronze/        # ingest + Textract parse
│   ├── silver/        # classify, extract, confidence blending
│   └── gold/          # auto-verdict routing, Aurora write
├── backend/           # FastAPI reviewer API
├── agent/             # LangGraph assistant agent service
├── frontend/          # React reviewer web app
├── infra/             # AWS CDK app (all stacks)
├── eval/              # MLflow eval dataset curation + prompt optimization jobs
└── .specs-fire/        # FIRE intents, work items, standards
```

### Conventions

- **One Lambda handler per file**: keep bronze/silver/gold steps independently testable and deployable
- **Shared code**: goes in a `common/` package installed as a local dependency, not copy-pasted across Lambda packages

## Import Order

```python
# 1. stdlib
import json
from datetime import datetime

# 2. third-party
import boto3
from pydantic import BaseModel

# 3. local
from common.models import ClaimDocument
```

**Rules**:
- Group stdlib / third-party / local, blank line between groups
- No wildcard imports

## Error Handling

### Pattern

**Approach**: raise typed exceptions internally, catch at the Lambda handler / FastAPI route boundary and translate to structured responses. Never swallow exceptions silently — this pipeline's whole point is surfacing low-confidence cases, not hiding failures.

### Guidelines

- Pipeline steps that fail on a single document must not crash the whole batch — log and route that document to a `failed` state, keep processing the rest
- Bedrock/Textract calls wrapped with explicit retry (boto3 built-in retry config) and a clear error surfaced if retries exhausted
- FastAPI routes return structured error bodies (`{"error": "...", "detail": "..."}`), never raw tracebacks

### Example

```python
class ExtractionError(Exception):
    """Raised when ai extraction fails after retries exhausted."""

def extract_fields(doc: ClaimDocument) -> ExtractionResult:
    try:
        return _call_bedrock_extract(doc)
    except BotoCoreError as e:
        raise ExtractionError(f"extract failed for {doc.id}: {e}") from e
```

## Logging

**Tool**: standard `logging` module (Python) configured for structured JSON output (CloudWatch-friendly); `console` in frontend dev only
**Format**: JSON lines with `timestamp`, `level`, `component`, `message`, `context` fields

### Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Local development detail (raw Textract/Bedrock payloads) |
| INFO | Normal pipeline progress (document ingested, verdict routed) |
| WARNING | Low-confidence routing, retry attempts |
| ERROR | Failed extraction, failed reviewer write, unhandled exceptions |

### Guidelines

**Always log**:
- Document ID + stage transitions (bronze → silver → gold)
- Confidence scores and routing decisions
- Reviewer verdict events

**Never log**:
- Full document contents/PII in plaintext at INFO level or above
- AWS credentials or secrets

## Comments and Documentation

### When to Comment

- Non-obvious business rules (e.g., why the confidence blend is 60/20/20, why 0.92 threshold) belong as a comment or docstring — these values won't be self-explanatory from code alone
- Skip comments that restate what the code obviously does

### Documentation Format

**Functions**: one-line docstring for non-trivial functions; full Google-style docstring only where params/behavior are non-obvious
**Classes**: one-line docstring stating purpose

## Code Patterns

### Preferred Patterns

#### Pydantic models at every boundary

Use Pydantic models for Lambda event payloads, FastAPI request/response bodies, and Bedrock structured-output parsing — one source of truth for shape + validation.

```python
class ExtractionResult(BaseModel):
    document_id: str
    fields: dict[str, str]
    field_confidences: dict[str, float]
```

### Anti-Patterns to Avoid

- **Hardcoded thresholds scattered across files**: keep `AUTO_VERDICT_THRESHOLD`, confidence weights, etc. in one `config.py` per component, not duplicated
- **Silent excepts**: `except Exception: pass` is banned — always log or re-raise
- **Direct Bedrock/Textract calls from React or FastAPI route bodies**: always go through a service/client wrapper so retries/mocking stay centralized

---
*Generated by specs.md - fabriqa.ai FIRE Flow*
