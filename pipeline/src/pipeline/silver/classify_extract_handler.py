import json
import logging
import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import ValidationError

from pipeline.silver.confidence_scoring import compute_composite_score
from pipeline.silver.models import EXPECTED_CLAIM_FIELDS, ClassificationResult, FieldExtraction

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Same Aurora Serverless v2 scale-to-zero cold-start behavior documented in
# the bronze handler and common/README.md.
_DATABASE_RESUMING_RETRY_SECONDS = 15

_CLASSIFY_TOOL = {
    "name": "classify_document",
    "description": "Classify the document type from its parsed text",
    "input_schema": {
        "type": "object",
        "properties": {"document_type": {"type": "string", "enum": ["medical_claim", "other"]}},
        "required": ["document_type"],
    },
}

_EXTRACT_TOOL = {
    "name": "extract_fields",
    "description": "Extract claim fields and a self-reported confidence (0.0-1.0) per field",
    "input_schema": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "field name -> extracted value; omit fields that are blank/missing",
            },
            "field_confidences": {
                "type": "object",
                "additionalProperties": {"type": "number"},
                "description": (
                    "field name -> confidence 0.0-1.0, one entry per field present in fields"
                ),
            },
        },
        "required": ["fields", "field_confidences"],
    },
}


def _rds_data_kwargs() -> dict:
    return {
        "resourceArn": os.environ["AURORA_CLUSTER_ARN"],
        "secretArn": os.environ["AURORA_SECRET_ARN"],
        "database": os.environ.get("AURORA_DATABASE_NAME", "claims_review"),
    }


def _execute_statement(rds_client, sql: str, parameters: list | None = None) -> dict:
    kwargs = _rds_data_kwargs()
    try:
        return rds_client.execute_statement(**kwargs, sql=sql, parameters=parameters or [])
    except ClientError as error:
        if error.response["Error"]["Code"] != "DatabaseResumingException":
            raise
        logger.warning(
            json.dumps({"stage": "silver-classify-extract", "event": "aurora_resuming_retry"})
        )
        time.sleep(_DATABASE_RESUMING_RETRY_SECONDS)
        return rds_client.execute_statement(**kwargs, sql=sql, parameters=parameters or [])


def _fetch_bronze_parse(rds_client, claim_id: str) -> tuple[list, float]:
    response = _execute_statement(
        rds_client,
        sql=(
            "SELECT raw_blocks, parse_confidence FROM bronze_parses "
            "WHERE claim_id = :claim_id::uuid"
        ),
        parameters=[{"name": "claim_id", "value": {"stringValue": claim_id}}],
    )
    record = response["records"][0]
    raw_blocks = json.loads(record[0]["stringValue"])
    parse_confidence = record[1]["doubleValue"]
    return raw_blocks, parse_confidence


def _reconstruct_text(raw_blocks: list) -> str:
    return "\n".join(
        block["Text"] for block in raw_blocks if block["BlockType"] == "LINE" and "Text" in block
    )


def _mark_claim_failed(rds_client, claim_id: str) -> None:
    _execute_statement(
        rds_client,
        sql="UPDATE claims SET status = 'failed', updated_at = now() WHERE id = :claim_id::uuid",
        parameters=[{"name": "claim_id", "value": {"stringValue": claim_id}}],
    )


def _update_claim_document_type(rds_client, claim_id: str, document_type: str) -> None:
    _execute_statement(
        rds_client,
        sql=(
            "UPDATE claims SET document_type = :document_type, updated_at = now() "
            "WHERE id = :claim_id::uuid"
        ),
        parameters=[
            {"name": "document_type", "value": {"stringValue": document_type}},
            {"name": "claim_id", "value": {"stringValue": claim_id}},
        ],
    )


def _insert_extraction(
    rds_client,
    claim_id: str,
    fields: dict,
    field_confidences: dict,
    parse_confidence: float,
    extract_confidence: float | None,
    completeness_score: float,
    composite_confidence: float,
) -> str:
    response = _execute_statement(
        rds_client,
        sql="""
            INSERT INTO extractions (
                claim_id, fields, field_confidences, parse_confidence,
                extract_confidence, completeness_score, composite_confidence, is_automated
            ) VALUES (
                :claim_id::uuid, :fields::jsonb, :field_confidences::jsonb, :parse_confidence,
                :extract_confidence, :completeness_score, :composite_confidence, false
            )
            RETURNING id
        """,
        parameters=[
            {"name": "claim_id", "value": {"stringValue": claim_id}},
            {"name": "fields", "value": {"stringValue": json.dumps(fields)}},
            {"name": "field_confidences", "value": {"stringValue": json.dumps(field_confidences)}},
            {"name": "parse_confidence", "value": {"doubleValue": parse_confidence}},
            {
                "name": "extract_confidence",
                "value": (
                    {"doubleValue": extract_confidence}
                    if extract_confidence is not None
                    else {"isNull": True}
                ),
            },
            {"name": "completeness_score", "value": {"doubleValue": completeness_score}},
            {"name": "composite_confidence", "value": {"doubleValue": composite_confidence}},
        ],
    )
    return response["records"][0][0]["stringValue"]


def _classify(bedrock_client, model_id: str, text: str) -> ClassificationResult:
    response = bedrock_client.invoke_model(
        modelId=model_id,
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "tools": [_CLASSIFY_TOOL],
                "tool_choice": {"type": "tool", "name": "classify_document"},
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Classify this parsed document text as either a medical claim "
                            'form ("medical_claim") or something else ("other"):\n\n' + text
                        ),
                    }
                ],
            }
        ),
    )
    body = json.loads(response["body"].read())
    tool_input = next(block["input"] for block in body["content"] if block["type"] == "tool_use")
    return ClassificationResult.model_validate(tool_input)


def _extract(bedrock_client, model_id: str, text: str) -> FieldExtraction:
    field_list = ", ".join(EXPECTED_CLAIM_FIELDS)
    response = bedrock_client.invoke_model(
        modelId=model_id,
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "tools": [_EXTRACT_TOOL],
                "tool_choice": {"type": "tool", "name": "extract_fields"},
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Extract these fields if present: {field_list}. A value of "
                            '"(blank)" means the field is missing - omit it from both fields '
                            f"and field_confidences. Parsed document text:\n\n{text}"
                        ),
                    }
                ],
            }
        ),
    )
    body = json.loads(response["body"].read())
    tool_input = next(block["input"] for block in body["content"] if block["type"] == "tool_use")
    return FieldExtraction.model_validate(tool_input)


def handler(event, context):
    """Silver classify+extract step: Bedrock classify + extract, composite score, persist to Aurora.

    Talks to Aurora via raw parameterized SQL over the RDS Data API, same
    reasoning as the bronze Lambda (see infra/README.md) — `common`'s
    SQLAlchemy stack pulls in a compiled psycopg dependency this project
    can't Docker-bundle. Pydantic *is* bundled here (see pipeline_stack.py's
    local-bundling helper) since it only needs prebuilt manylinux wheels,
    unlike psycopg.
    """
    claim_id = event["claim_id"]
    model_id = os.environ["BEDROCK_MODEL_ID"]

    rds_client = boto3.client("rds-data")
    bedrock_client = boto3.client(
        "bedrock-runtime", config=Config(retries={"max_attempts": 5, "mode": "adaptive"})
    )

    raw_blocks, parse_confidence = _fetch_bronze_parse(rds_client, claim_id)
    text = _reconstruct_text(raw_blocks)

    fields: dict[str, str] = {}
    field_confidences: dict[str, float] = {}
    try:
        classification = _classify(bedrock_client, model_id, text)

        if classification.document_type == "medical_claim":
            extraction = _extract(bedrock_client, model_id, text)
            fields = extraction.fields
            field_confidences = extraction.field_confidences
    except (ClientError, ValidationError, StopIteration):
        logger.exception(
            json.dumps(
                {
                    "stage": "silver-classify-extract",
                    "claim_id": claim_id,
                    "event": "bedrock_failed",
                }
            )
        )
        _mark_claim_failed(rds_client, claim_id)
        raise

    _update_claim_document_type(rds_client, claim_id, classification.document_type)

    completeness_score = len(fields) / len(EXPECTED_CLAIM_FIELDS)
    extract_confidence = (
        sum(field_confidences.values()) / len(field_confidences) if field_confidences else None
    )
    composite_confidence = compute_composite_score(
        extract_confidence=extract_confidence,
        parse_confidence=parse_confidence,
        completeness_score=completeness_score,
    )

    extraction_id = _insert_extraction(
        rds_client,
        claim_id,
        fields,
        field_confidences,
        parse_confidence,
        extract_confidence,
        completeness_score,
        composite_confidence,
    )

    logger.info(
        json.dumps(
            {
                "stage": "silver-classify-extract",
                "claim_id": claim_id,
                "document_type": classification.document_type,
                "composite_confidence": composite_confidence,
            }
        )
    )
    return {
        "claim_id": claim_id,
        "extraction_id": extraction_id,
        "composite_confidence": composite_confidence,
    }
