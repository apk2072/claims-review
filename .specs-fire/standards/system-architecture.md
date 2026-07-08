# System Architecture

## Overview

An AI-native medical claims document review platform, built on AWS as a learning mirror of a Databricks reference architecture (Unity Catalog / Delta Lake / Lakeflow / Lakebase / MLflow). Replaces brittle rules-based OCR with LLM-based document parsing, routes low-confidence extractions to human reviewers, and closes the loop by feeding reviewer corrections into an automated evaluation + prompt-optimization cycle for an assistant agent.

## System Context

A single reviewer-facing web app backed by an event-driven document pipeline and a conversational agent, all sharing one Aurora Postgres instance as the operational system of record.

### Context Diagram

```
                    ┌─────────────────────┐
   Claim PDFs/images│                     │
   ─────────────────▶       S3 Bucket      │
                    │                     │
                    └──────────┬──────────┘
                               │ event
                               ▼
                    ┌─────────────────────┐
                    │   Document Pipeline  │
                    │ (Bronze/Silver/Gold) │
                    └──────────┬──────────┘
                               │ writes
                               ▼
                    ┌─────────────────────┐        ┌───────────────────┐
                    │  Aurora Serverless   │◀──────▶│  Reviewer Web App  │◀── Human reviewer
                    │  v2 (Postgres+pgvec) │        │ (React + FastAPI)  │
                    └──────────┬──────────┘        └───────────────────┘
                               │ traces/verdicts               ▲
                               ▼                                │ chat
                    ┌─────────────────────┐                     │
                    │   MLflow (tracing,   │◀────────────────────┘
                    │  eval, prompt reg.)  │        Assistant Agent
                    └──────────┬──────────┘        (LangGraph + Bedrock)
                               │ optimize
                               ▼
                    ┌─────────────────────┐
                    │  GEPA-based prompt   │
                    │     optimization     │
                    └─────────────────────┘
```

### Users

- **Claims reviewer**: reviews low-confidence extractions, approves/rejects/corrects fields, chats with the assistant agent about extraction/review data
- **Supervisor**: monitors reviewer performance and pipeline accuracy dashboards, bookmarks traces for evaluation
- **Project owner (learner)**: operates and extends the system for interview-prep purposes

### External Systems

- **Amazon Textract**: document OCR — bounding boxes, per-element confidence
- **Amazon Bedrock (Claude models)**: document classification, structured field extraction, assistant agent reasoning
- **AWS Step Functions / Lambda**: pipeline orchestration and incremental processing

## Architecture Pattern

**Pattern**: Event-driven medallion pipeline (Bronze/Silver/Gold) feeding an operational Postgres store, plus a separate stateful agent service and an offline evaluation/optimization loop
**Rationale**: Mirrors the layered structure of the original Databricks architecture (Lakehouse Intelligence → Operational Insights → Learning Loop) so the mapping between platforms stays legible for interview discussion, while using AWS-native equivalents for each layer.

## Component Architecture

### Components

#### Bronze/Silver/Gold Pipeline

- **Purpose**: turn raw claim documents into confidence-scored, auto-verdicted structured data
- **Responsibilities**: S3 ingest, Textract parse (bronze), Bedrock classify + extract (silver), confidence blending + auto-verdict routing (gold), write to Aurora
- **Dependencies**: S3, Textract, Bedrock, Step Functions, Aurora

#### Reviewer Backend (FastAPI)

- **Purpose**: serve the reviewer web app's data and verdict-recording API
- **Responsibilities**: expose extraction queue, record atomic verdicts (status + audit row + metrics + MLflow trace tag), dashboard aggregates
- **Dependencies**: Aurora, MLflow

#### Reviewer Frontend (React)

- **Purpose**: reviewer-facing UI — dashboard, review queue, document/field side-by-side view, assistant chat
- **Responsibilities**: render extraction queue and dashboards, submit verdicts, host assistant chat UI
- **Dependencies**: Reviewer Backend API, Assistant Agent (via SSE)

#### Assistant Agent (LangGraph + Bedrock)

- **Purpose**: stateful, natural-language interface over the operational data for reviewers/supervisors
- **Responsibilities**: multi-turn conversation with persisted checkpoints, tool calls against Aurora, long-term per-user memory via pgvector
- **Dependencies**: Bedrock, Aurora (checkpoint + memory tables), MLflow (tracing)

#### Eval & Prompt Optimization Loop

- **Purpose**: turn human review verdicts into an automated prompt-improvement cycle for the assistant agent
- **Responsibilities**: weekly curation of high-signal traces, weighted composite scoring, GEPA-based challenger prompt generation, promotion gate, publish to MLflow Prompt Registry
- **Dependencies**: MLflow, Bedrock (for the agent being optimized and for LLM-as-judge scoring)

### Component Diagram

```
pipeline/  ──writes──▶  Aurora  ◀──reads/writes──  backend/  ◀──serves──  frontend/
                            ▲                                                 │
                            │                                                 │ chat (SSE)
                            └──────────────────  agent/  ◀──────────────────┘
                                                    │
                                                    ▼
                                              MLflow traces
                                                    │
                                                    ▼
                                              eval/ (curation → GEPA → promotion)
                                                    │
                                                    ▼
                                        agent/ system prompt (next version)
```

## Data Flow

Claim document → Textract parse → Bedrock classify + extract → confidence blend → auto-verdict routing → Aurora → reviewer app (auto-approved bypass review; low-confidence queued) → reviewer verdict → atomic write (status + audit + metrics + MLflow tag) → weekly eval curation → GEPA prompt optimization → promotion gate → updated agent prompt.

```
[S3: PDF/image landed]
  → [Bronze: Textract AnalyzeDocument] (bounding boxes, per-element confidence)
  → [Silver: Bedrock classify] (document type)
  → [Silver: Bedrock extract] (field/value pairs, per-field confidence)
  → [Silver: composite confidence = 0.6*extract + 0.2*parse + 0.2*completeness]
  → [Gold: confidence > 0.92 ?]
      ├─ yes → auto_verdict = true → Aurora (auto-approved)
      └─ no  → Aurora (queued for human review)
  → [Reviewer app: approve/reject/correct]
  → [Atomic verdict write: status + audit row + metric + MLflow trace tag]
  → [Weekly curation: human_feedback + failed-scorer + bookmarked traces]
  → [GEPA prompt optimization: generate challenger, train/holdout split]
  → [Promotion gate: safety floor, correctness floor, bootstrap CI]
  → [MLflow Prompt Registry: champion prompt updated]
  → [Assistant agent uses new champion prompt]
```

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Ingest | S3 + S3 Event Notifications | Land raw claim documents, trigger pipeline |
| Parse | Amazon Textract | OCR, bounding boxes, per-element confidence |
| Classify/Extract | Amazon Bedrock (Claude) | Document type classification, structured field extraction |
| Orchestration | AWS Step Functions + Lambda | Bronze/silver/gold pipeline steps |
| Operational store | Aurora Serverless v2 (Postgres + pgvector) | System of record, audit trail, agent memory |
| Backend API | FastAPI on ECS Fargate | Reviewer app data + verdict API |
| Frontend | React + Vite on CloudFront/S3 | Reviewer web app |
| Agent | LangGraph + Bedrock on ECS Fargate | Stateful assistant agent |
| Tracing/Eval | MLflow (self-hosted or SageMaker Managed) | Tracing, evaluation datasets, prompt registry |
| Prompt optimization | GEPA (Python, framework-agnostic) | Challenger prompt generation from curated failures |
| IaC | AWS CDK (Python) | All infrastructure definition and deployment |

## Non-Functional Requirements

### Performance

- **Pipeline latency**: a batch of synthetic documents should flow bronze→gold in well under a minute for demo purposes (no strict SLA — this is a learning project, not production)
- **Reviewer app responsiveness**: queue and dashboard views should load in under 2s against realistic (hundreds of rows) synthetic data volumes

### Security

- No real PHI ever — synthetic claim data only
- IAM least-privilege per Lambda/ECS task role
- No secrets in source control — env vars / Secrets Manager only
- Aurora access scoped per-service via IAM database authentication where practical

### Scalability

Not a design priority for this project — serverless/scale-to-zero components chosen primarily to keep AWS cost low when idle, not to satisfy a load target.

## Constraints

- Owner-operated AWS account, default profile, `us-east-1` region
- Real AWS costs are acceptable but should be kept small — favor serverless/pay-per-use and scale-to-zero (Aurora Serverless v2, Fargate, Lambda) over always-on provisioned resources
- Bedrock and Textract are pay-per-use from day one (no free tier equivalent to Databricks Free Edition) — test suites must mock these, only manual verification runs hit real endpoints
- Single-developer project — no CI/CD gate required, but standards documents still apply so the code stays interview-explainable

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Document parsing | Amazon Textract over a custom OCR model | Textract natively returns bounding boxes + confidence, matching `ai_parse_document`'s output shape |
| Classification/extraction | Bedrock (Claude) with structured prompts over Amazon Comprehend | Comprehend custom classifiers need training data; Bedrock/Claude gives the same "AI-native, few-shot, no training pipeline" property as Databricks' `ai_classify`/`ai_extract` |
| Operational store | Aurora Serverless v2 Postgres over DynamoDB | Needs relational joins for audit trail + dashboard aggregates, and pgvector for agent memory — matches Lakebase's role directly |
| Agent hosting | ECS Fargate over Lambda | Needs long-lived stateful SSE connections and persistent connection pools, same reasoning the original architecture gives for using a Databricks App instead of a model-serving endpoint |
| Tracing/eval | MLflow (self-hosted or SageMaker Managed) | Keeps the same tracing/eval/prompt-registry vocabulary as the reference architecture instead of building bespoke tooling |
| IaC tool | AWS CDK (Python) over Terraform | Single language across the whole project; easier for a Python-primary learner to read and modify infra code |

---
*Generated by specs.md - fabriqa.ai FIRE Flow*
