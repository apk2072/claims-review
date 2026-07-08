---
id: mlflow-tracing-setup
title: MLflow tracing setup
intent: claims-review-platform
complexity: medium
mode: confirm
status: pending
depends_on: [assistant-agent-service]
created: 2026-07-05T00:00:00Z
---

# Work Item: MLflow tracing setup

## Description

Stand up an MLflow tracking server (self-hosted on Fargate with S3 artifact store + Aurora/SQLite backend store, or SageMaker Managed MLflow if it proves faster to stand up) and wire MLflow's auto-tracing into the LangGraph/Bedrock agent so every conversation turn produces a trace tagged with `prompt_version`, session, and user metadata.

## Acceptance Criteria

- [ ] MLflow tracking server reachable from the agent service
- [ ] Every agent turn produces an MLflow trace capturing tool calls and model I/O
- [ ] Traces tagged with `prompt_version`, `mlflow.trace.session` (thread ID), `mlflow.trace.user`
- [ ] A live conversation with the agent (from work item 11) is visible as traces in the MLflow UI
- [ ] Reviewer verdict submission (work item 9) tags the corresponding trace with `human_feedback = approved|rejected|corrected`

## Technical Notes

Prefer SageMaker Managed MLflow if available and quick to provision — self-hosting MLflow adds infra surface area that isn't the point of this work item. Fall back to self-hosted only if managed MLflow isn't readily available in the account.

## Dependencies

- assistant-agent-service
