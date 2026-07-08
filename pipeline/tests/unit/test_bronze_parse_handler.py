import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from pipeline.bronze.parse_handler import handler

_FIXTURES_DIR = pathlib.Path(__file__).parents[1] / "fixtures" / "textract_responses"


def _load_textract_fixture(name: str) -> dict:
    return json.loads((_FIXTURES_DIR / f"{name}.json").read_text())


def _event(bucket: str = "claim-documents", key: str = "claims/sample.png") -> dict:
    return {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}


@pytest.fixture(autouse=True)
def _aurora_env(monkeypatch):
    monkeypatch.setenv("AURORA_CLUSTER_ARN", "arn:aws:rds:us-east-1:123456789012:cluster:test")
    monkeypatch.setenv(
        "AURORA_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
    )
    monkeypatch.setenv("AURORA_DATABASE_NAME", "claims_review")


def _mock_rds_client(claim_id: str = "11111111-1111-1111-1111-111111111111") -> MagicMock:
    client = MagicMock()
    client.execute_statement.return_value = {"records": [[{"stringValue": claim_id}]]}
    return client


def _boto_client_stub(rds_client, textract_client):
    def _client(service_name, **kwargs):
        if service_name == "rds-data":
            return rds_client
        if service_name == "textract":
            return textract_client
        raise AssertionError(f"unexpected boto3.client call for {service_name}")

    return _client


def test_bronze_parse_handler_clean_document_returns_high_confidence():
    rds_client = _mock_rds_client()
    textract_client = MagicMock()
    textract_client.analyze_document.return_value = _load_textract_fixture("clean_high_confidence")

    with patch(
        "pipeline.bronze.parse_handler.boto3.client",
        side_effect=_boto_client_stub(rds_client, textract_client),
    ):
        result = handler(_event(key="claims/clean.png"), None)

    assert result["claim_id"] == "11111111-1111-1111-1111-111111111111"
    assert result["parse_confidence"] > 0.9

    # claim upsert, then bronze_parses upsert — no failure-path UPDATE
    assert rds_client.execute_statement.call_count == 2
    bronze_parse_sql = rds_client.execute_statement.call_args_list[1].kwargs["sql"]
    assert "INSERT INTO bronze_parses" in bronze_parse_sql


def test_bronze_parse_handler_blurry_document_yields_lower_confidence_than_clean():
    rds_client = _mock_rds_client()
    textract_client = MagicMock()
    textract_client.analyze_document.return_value = _load_textract_fixture("blurry_low_confidence")

    with patch(
        "pipeline.bronze.parse_handler.boto3.client",
        side_effect=_boto_client_stub(rds_client, textract_client),
    ):
        blurry_result = handler(_event(key="claims/blurry.png"), None)

    rds_client_clean = _mock_rds_client()
    textract_client_clean = MagicMock()
    textract_client_clean.analyze_document.return_value = _load_textract_fixture(
        "clean_high_confidence"
    )
    with patch(
        "pipeline.bronze.parse_handler.boto3.client",
        side_effect=_boto_client_stub(rds_client_clean, textract_client_clean),
    ):
        clean_result = handler(_event(key="claims/clean.png"), None)

    assert blurry_result["parse_confidence"] < clean_result["parse_confidence"]


def test_bronze_parse_handler_textract_permanent_failure_marks_claim_failed_and_reraises():
    rds_client = _mock_rds_client()
    textract_client = MagicMock()
    textract_client.analyze_document.side_effect = RuntimeError("Textract retries exhausted")

    with (
        patch(
            "pipeline.bronze.parse_handler.boto3.client",
            side_effect=_boto_client_stub(rds_client, textract_client),
        ),
        pytest.raises(RuntimeError, match="Textract retries exhausted"),
    ):
        handler(_event(key="claims/broken.png"), None)

    # claim upsert, then the failed-status UPDATE — no bronze_parses insert
    assert rds_client.execute_statement.call_count == 2
    failed_update_sql = rds_client.execute_statement.call_args_list[1].kwargs["sql"]
    assert "SET status = 'failed'" in failed_update_sql


def test_bronze_parse_handler_retries_once_on_aurora_database_resuming():
    resuming_error = ClientError(
        {"Error": {"Code": "DatabaseResumingException", "Message": "resuming after auto-pause"}},
        "ExecuteStatement",
    )
    rds_client = MagicMock()
    rds_client.execute_statement.side_effect = [
        resuming_error,
        {"records": [[{"stringValue": "11111111-1111-1111-1111-111111111111"}]]},
        {},  # bronze_parses upsert
    ]
    textract_client = MagicMock()
    textract_client.analyze_document.return_value = _load_textract_fixture("clean_high_confidence")

    with (
        patch(
            "pipeline.bronze.parse_handler.boto3.client",
            side_effect=_boto_client_stub(rds_client, textract_client),
        ),
        patch("pipeline.bronze.parse_handler.time.sleep") as mock_sleep,
    ):
        result = handler(_event(key="claims/clean.png"), None)

    assert result["claim_id"] == "11111111-1111-1111-1111-111111111111"
    mock_sleep.assert_called_once_with(15)
    assert rds_client.execute_statement.call_count == 3
