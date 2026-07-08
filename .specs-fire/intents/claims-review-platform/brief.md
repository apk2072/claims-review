---
id: claims-review-platform
title: AI-Native Medical Claims Review Platform (AWS)
status: in_progress
created: 2026-07-05T00:00:00Z
---

# Intent: AI-Native Medical Claims Review Platform (AWS)

## Goal

Build and deploy a working AI-native medical claims review platform on AWS, mirroring a Databricks reference architecture layer-by-layer, as a hands-on interview-prep project. Prioritize an actually-running system over documentation-only prep — each stage should be demoable as it's completed.

## Users

- **Project owner**: plays both "reviewer" and "supervisor" roles to exercise the system end-to-end
- **Real audience**: a Databricks interviewer, who the owner wants to be able to speak to fluently about every design choice and its Databricks-analog

## Problem

Reading the reference blog gives vocabulary, not depth. Building the AWS-analog system forces reasoning through the medallion pipeline, AI-native document processing, agent design, and the human-feedback → eval → prompt-optimization loop, so the owner can defend design decisions in an interview rather than recite them.

## Success Criteria

- End-to-end pipeline processes synthetic claim documents: S3 ingest → Textract parse → Bedrock classify/extract → confidence blend → auto-verdict routing → Aurora
- Reviewer web app shows the queue and records human verdicts (approve/reject/correct) with atomic writes (status update + audit row + metrics + trace tag)
- Assistant agent (LangGraph + Bedrock) answers natural-language questions over review data, with persisted per-user memory
- Evaluation loop runs at least once for real: verdicts → curated eval dataset → GEPA prompt optimization → promotion gate → updated agent prompt
- Owner can explain every AWS service choice and its Databricks-analog cold, in interview terms

## Constraints

- AWS default profile, `us-east-1`, real costs acceptable but kept small (serverless/scale-to-zero preferred)
- Synthetic claims data only — never real PHI
- Solo project, no CI/CD required
- **Hard deadline: interview on 2026-07-10 (5 days from intent capture)** — sequencing favors a working, incrementally-deployable system over exhaustive breadth; each work item should leave the system in a demoable state
- Built incrementally, one work item at a time, checkpointed per FIRE's "balanced" autonomy mode

## Notes

Reference architecture being mirrored (Databricks → AWS):

| Databricks | AWS |
|---|---|
| Auto Loader + UC Volume | S3 + Event Notifications |
| `ai_parse_document` | Amazon Textract |
| `ai_classify` / `ai_extract` | Amazon Bedrock (Claude) |
| Unity Catalog | (skipped — no direct AWS analog needed for this scope) |
| Lakeflow | Step Functions + Lambda |
| Lakebase (Postgres) | Aurora Serverless v2 (Postgres + pgvector) |
| Databricks Apps | ECS Fargate |
| Foundation Model API | Amazon Bedrock |
| MLflow | MLflow (self-hosted or SageMaker Managed) |
| GEPA prompt optimization | Same (framework-agnostic Python) |

Given the 5-day deadline, expect work-item decomposition to front-load the pipeline (highest interview-relevance, most distinctive vs. generic CRUD apps) and treat the eval/prompt-optimization loop as the capstone item that ties everything together.
