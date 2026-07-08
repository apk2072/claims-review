from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from pipeline.gold.confidence_route_handler import handler


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AURORA_CLUSTER_ARN", "arn:aws:rds:us-east-1:123456789012:cluster:test")
    monkeypatch.setenv(
        "AURORA_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
    )
    monkeypatch.setenv("AURORA_DATABASE_NAME", "claims_review")


def _event(composite_confidence: float) -> dict:
    return {
        "claim_id": "11111111-1111-1111-1111-111111111111",
        "extraction_id": "22222222-2222-2222-2222-222222222222",
        "composite_confidence": composite_confidence,
    }


def _boto_client_stub(rds_client):
    def _client(service_name, **kwargs):
        if service_name == "rds-data":
            return rds_client
        raise AssertionError(f"unexpected boto3.client call for {service_name}")

    return _client


def test_gold_handler_above_threshold_auto_verifies():
    rds_client = MagicMock()
    rds_client.execute_statement.return_value = {}

    with patch(
        "pipeline.gold.confidence_route_handler.boto3.client",
        side_effect=_boto_client_stub(rds_client),
    ):
        result = handler(_event(0.96), None)

    assert result["is_automated"] is True

    extraction_update_sql = rds_client.execute_statement.call_args_list[0].kwargs["sql"]
    assert "UPDATE extractions SET is_automated" in extraction_update_sql
    extraction_params = {
        p["name"]: p["value"]
        for p in rds_client.execute_statement.call_args_list[0].kwargs["parameters"]
    }
    assert extraction_params["is_automated"] == {"booleanValue": True}

    claim_update_sql = rds_client.execute_statement.call_args_list[1].kwargs["sql"]
    claim_params = {
        p["name"]: p["value"]
        for p in rds_client.execute_statement.call_args_list[1].kwargs["parameters"]
    }
    assert "UPDATE claims SET status" in claim_update_sql
    assert claim_params["status"] == {"stringValue": "auto_verified"}


def test_gold_handler_at_or_below_threshold_queues_for_human_review():
    rds_client = MagicMock()
    rds_client.execute_statement.return_value = {}

    with patch(
        "pipeline.gold.confidence_route_handler.boto3.client",
        side_effect=_boto_client_stub(rds_client),
    ):
        result = handler(_event(0.89), None)

    assert result["is_automated"] is False

    claim_params = {
        p["name"]: p["value"]
        for p in rds_client.execute_statement.call_args_list[1].kwargs["parameters"]
    }
    assert claim_params["status"] == {"stringValue": "human_review"}


def test_gold_handler_aurora_failure_marks_claim_failed_and_reraises():
    rds_client = MagicMock()
    rds_client.execute_statement.side_effect = ClientError(
        {"Error": {"Code": "InternalServerErrorException", "Message": "boom"}}, "ExecuteStatement"
    )

    with (
        patch(
            "pipeline.gold.confidence_route_handler.boto3.client",
            side_effect=_boto_client_stub(rds_client),
        ),
        pytest.raises(ClientError),
    ):
        handler(_event(0.96), None)

    failed_update_sql = rds_client.execute_statement.call_args_list[-1].kwargs["sql"]
    assert "SET status = 'failed'" in failed_update_sql
