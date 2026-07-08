import json
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

from pipeline.gold.verdict_routing import DEFAULT_AUTO_VERDICT_THRESHOLD, route_verdict

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Same Aurora Serverless v2 scale-to-zero cold-start behavior documented in
# the bronze/silver handlers and common/README.md.
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
        logger.warning(
            json.dumps({"stage": "gold-confidence-route", "event": "aurora_resuming_retry"})
        )
        time.sleep(_DATABASE_RESUMING_RETRY_SECONDS)
        return rds_client.execute_statement(**kwargs, sql=sql, parameters=parameters or [])


def _mark_claim_failed(rds_client, claim_id: str) -> None:
    _execute_statement(
        rds_client,
        sql="UPDATE claims SET status = 'failed', updated_at = now() WHERE id = :claim_id::uuid",
        parameters=[{"name": "claim_id", "value": {"stringValue": claim_id}}],
    )


def _update_extraction_verdict(rds_client, extraction_id: str, is_automated: bool) -> None:
    _execute_statement(
        rds_client,
        sql="UPDATE extractions SET is_automated = :is_automated WHERE id = :extraction_id::uuid",
        parameters=[
            {"name": "is_automated", "value": {"booleanValue": is_automated}},
            {"name": "extraction_id", "value": {"stringValue": extraction_id}},
        ],
    )


def _update_claim_status(rds_client, claim_id: str, status: str) -> None:
    _execute_statement(
        rds_client,
        sql="UPDATE claims SET status = :status, updated_at = now() WHERE id = :claim_id::uuid",
        parameters=[
            {"name": "status", "value": {"stringValue": status}},
            {"name": "claim_id", "value": {"stringValue": claim_id}},
        ],
    )


def handler(event, context):
    """Gold confidence-route step: threshold routing + final claims/extractions status update.

    Last state in the pipeline. Talks to Aurora via raw parameterized SQL
    over the RDS Data API, same reasoning as bronze/silver (see
    infra/README.md).
    """
    claim_id = event["claim_id"]
    extraction_id = event["extraction_id"]
    composite_confidence = event["composite_confidence"]
    threshold = float(os.environ.get("AUTO_VERDICT_THRESHOLD", DEFAULT_AUTO_VERDICT_THRESHOLD))

    rds_client = boto3.client("rds-data")

    try:
        is_automated = route_verdict(composite_confidence, threshold)
        _update_extraction_verdict(rds_client, extraction_id, is_automated)
        _update_claim_status(
            rds_client, claim_id, "auto_verified" if is_automated else "human_review"
        )
    except ClientError:
        logger.exception(
            json.dumps(
                {
                    "stage": "gold-confidence-route",
                    "claim_id": claim_id,
                    "event": "routing_failed",
                }
            )
        )
        _mark_claim_failed(rds_client, claim_id)
        raise

    logger.info(
        json.dumps(
            {
                "stage": "gold-confidence-route",
                "claim_id": claim_id,
                "is_automated": is_automated,
                "composite_confidence": composite_confidence,
            }
        )
    )
    return {
        "claim_id": claim_id,
        "extraction_id": extraction_id,
        "is_automated": is_automated,
        "composite_confidence": composite_confidence,
    }
