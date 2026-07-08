# claims-review

AI-native medical claims review platform on AWS — built as a hands-on interview-prep project mirroring a Databricks reference architecture (Unity Catalog / Delta Lake / Lakeflow / Lakebase / MLflow) using AWS-native equivalents (Textract, Bedrock, Aurora, Step Functions, ECS Fargate, MLflow).

**This project only ever processes synthetic claims data — never real PHI.**

## Structure

| Path | Purpose |
|------|---------|
| `pipeline/` | Bronze/Silver/Gold document processing (Textract + Bedrock, Step Functions) |
| `backend/` | FastAPI reviewer API |
| `agent/` | LangGraph + Bedrock stateful assistant agent |
| `frontend/` | React + Vite reviewer web app |
| `eval/` | Eval curation, weighted scoring, GEPA prompt optimization |
| `common/` | Shared models/config used across the Python components |
| `infra/` | AWS CDK (Python) app — all infrastructure |
| `.specs-fire/` | FIRE project docs: intent, work items, standards, run history |

See [`.specs-fire/standards/system-architecture.md`](.specs-fire/standards/system-architecture.md) for the full architecture and Databricks→AWS component mapping.

## Setup

```bash
# Python components (uv workspace)
uv sync --all-packages

# Frontend
cd frontend && npm install

# CDK CLI
npm install -g aws-cdk
```

## AWS

- Default AWS CLI profile, region `us-east-1`
- Real AWS costs apply — see `infra/README.md` for cost-control notes and teardown commands
