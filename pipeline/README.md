# pipeline

Bronze/Silver/Gold claim document processing pipeline.

- **Bronze**: S3-triggered Lambda calls Amazon Textract to parse documents (bounding boxes + confidence).
- **Silver**: Lambda calls Amazon Bedrock (Claude) to classify document type and extract structured fields with confidence, then computes the composite confidence score (60% extract, 20% parse, 20% completeness).
- **Gold**: Lambda applies the auto-verdict confidence threshold (default 0.92) and writes the final routed record to Aurora.

Orchestrated by an AWS Step Functions state machine (see `infra/`).

## Run locally

```bash
uv run --package pipeline python -c "print('ok')"
uv run --package pipeline pytest
```
