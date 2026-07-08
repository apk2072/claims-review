import json
import logging
import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Textract blocks worth keeping for downstream silver/gold steps and for the
# raw audit record; drops Textract's internal-only fields (Polygon points,
# Relationships graph) that aren't needed once we have BoundingBox + Text.
_KEPT_BLOCK_FIELDS = ("BlockType", "Text", "Confidence", "Geometry")

# Aurora Serverless v2 scale-to-zero cold-start: the first Data API call
# after an idle period raises this and succeeds on retry ~15s later. Seen
# repeatedly across this project (see common/README.md) — worth one bounded
# retry here since, unlike the manual verification runs elsewhere, nothing
# is watching this Lambda to retry by hand.
_DATABASE_RESUMING_RETRY_SECONDS = 15


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
        logger.warning(json.dumps({"stage": "bronze-parse", "event": "aurora_resuming_retry"}))
        time.sleep(_DATABASE_RESUMING_RETRY_SECONDS)
        return rds_client.execute_statement(**kwargs, sql=sql, parameters=parameters or [])


def _upsert_claim(rds_client, s3_key: str) -> str:
    """Insert (or reuse) the claims row for this S3 key, returning its id."""
    response = _execute_statement(
        rds_client,
        sql="""
            INSERT INTO claims (s3_key, status)
            VALUES (:s3_key, 'processing')
            ON CONFLICT (s3_key) DO UPDATE SET updated_at = now()
            RETURNING id
        """,
        parameters=[{"name": "s3_key", "value": {"stringValue": s3_key}}],
    )
    return response["records"][0][0]["stringValue"]


def _mark_claim_failed(rds_client, claim_id: str) -> None:
    _execute_statement(
        rds_client,
        sql="UPDATE claims SET status = 'failed', updated_at = now() WHERE id = :claim_id::uuid",
        parameters=[{"name": "claim_id", "value": {"stringValue": claim_id}}],
    )


def _upsert_bronze_parse(
    rds_client, claim_id: str, raw_blocks: list, parse_confidence: float
) -> None:
    _execute_statement(
        rds_client,
        sql="""
            INSERT INTO bronze_parses (claim_id, raw_blocks, parse_confidence)
            VALUES (:claim_id::uuid, :raw_blocks::jsonb, :parse_confidence)
            ON CONFLICT (claim_id) DO UPDATE SET
                raw_blocks = EXCLUDED.raw_blocks,
                parse_confidence = EXCLUDED.parse_confidence,
                created_at = now()
        """,
        parameters=[
            {"name": "claim_id", "value": {"stringValue": claim_id}},
            {"name": "raw_blocks", "value": {"stringValue": json.dumps(raw_blocks)}},
            {"name": "parse_confidence", "value": {"doubleValue": parse_confidence}},
        ],
    )


def _trim_blocks(blocks: list) -> list:
    return [{k: block[k] for k in _KEPT_BLOCK_FIELDS if k in block} for block in blocks]


def _compute_parse_confidence(blocks: list) -> float:
    """Mean confidence of WORD blocks, normalized from Textract's 0-100 to 0-1."""
    word_confidences = [b["Confidence"] for b in blocks if b["BlockType"] == "WORD"]
    if not word_confidences:
        return 0.0
    return (sum(word_confidences) / len(word_confidences)) / 100


def handler(event, context):
    """Bronze-parse step: Textract AnalyzeDocument (FORMS) + persist to Aurora.

    Talks to Aurora via raw parameterized SQL over the RDS Data API rather
    than the `common` package's SQLAlchemy models. `common` pulls in
    psycopg[binary] (a compiled dependency), and this Lambda is deployed via
    Code.from_inline with no Docker-based bundling available on this
    machine — see infra/README.md. The Data API is also how Alembic already
    reaches this same Aurora cluster from outside its VPC.
    """
    bucket = event["detail"]["bucket"]["name"]
    key = event["detail"]["object"]["key"]

    rds_client = boto3.client("rds-data")
    claim_id = _upsert_claim(rds_client, key)

    textract_client = boto3.client(
        "textract", config=Config(retries={"max_attempts": 5, "mode": "adaptive"})
    )
    try:
        response = textract_client.analyze_document(
            Document={"S3Object": {"Bucket": bucket, "Name": key}},
            FeatureTypes=["FORMS"],
        )
    except Exception:
        logger.exception(
            json.dumps({"stage": "bronze-parse", "claim_id": claim_id, "event": "textract_failed"})
        )
        _mark_claim_failed(rds_client, claim_id)
        raise

    blocks = response["Blocks"]
    parse_confidence = _compute_parse_confidence(blocks)
    raw_blocks = _trim_blocks(blocks)
    _upsert_bronze_parse(rds_client, claim_id, raw_blocks, parse_confidence)

    logger.info(
        json.dumps(
            {
                "stage": "bronze-parse",
                "claim_id": claim_id,
                "parse_confidence": parse_confidence,
            }
        )
    )
    return {
        "claim_id": claim_id,
        "bucket": bucket,
        "key": key,
        "parse_confidence": parse_confidence,
    }
