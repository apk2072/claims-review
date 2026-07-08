import io
import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from pipeline.silver.classify_extract_handler import handler
from pipeline.silver.models import EXPECTED_CLAIM_FIELDS

_FIXTURES_DIR = pathlib.Path(__file__).parents[1] / "fixtures" / "bedrock_responses"


def _load_bedrock_fixture(name: str) -> dict:
    return {"body": io.BytesIO((_FIXTURES_DIR / f"{name}.json").read_bytes())}


def _mock_bedrock_response(payload: dict) -> dict:
    return {"body": io.BytesIO(json.dumps(payload).encode())}


def _mock_tool_use_payload(tool_name: str, tool_input: dict) -> dict:
    return {"content": [{"type": "tool_use", "name": tool_name, "input": tool_input}]}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AURORA_CLUSTER_ARN", "arn:aws:rds:us-east-1:123456789012:cluster:test")
    monkeypatch.setenv(
        "AURORA_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
    )
    monkeypatch.setenv("AURORA_DATABASE_NAME", "claims_review")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")


def _rds_client_for(claim_id: str, raw_blocks: list, parse_confidence: float) -> MagicMock:
    client = MagicMock()
    client.execute_statement.return_value = {
        "records": [
            [
                {"stringValue": json.dumps(raw_blocks)},
                {"doubleValue": parse_confidence},
            ]
        ]
    }
    # Subsequent calls (document_type update, extraction insert) don't need
    # the bronze_parses SELECT shape — override per-test where the return
    # value's exact content matters (e.g. the RETURNING id from the insert).
    return client


def _line_blocks(*texts: str) -> list:
    return [{"BlockType": "LINE", "Text": t} for t in texts]


def _boto_client_stub(rds_client, bedrock_client):
    def _client(service_name, **kwargs):
        if service_name == "rds-data":
            return rds_client
        if service_name == "bedrock-runtime":
            return bedrock_client
        raise AssertionError(f"unexpected boto3.client call for {service_name}")

    return _client


def _event(claim_id: str = "11111111-1111-1111-1111-111111111111") -> dict:
    return {
        "claim_id": claim_id,
        "bucket": "claim-documents",
        "key": "claims/sample.png",
        "parse_confidence": 0.98,
    }


def test_silver_handler_clean_document_yields_high_composite_confidence():
    rds_client = _rds_client_for(
        "c1", _line_blocks("SYNTHETIC MEDICAL CLAIM FORM", "Jane Test Doe"), 0.98
    )
    # bronze_parses SELECT, then document_type UPDATE, then extraction INSERT (RETURNING id)
    rds_client.execute_statement.side_effect = [
        rds_client.execute_statement.return_value,
        {},
        {"records": [[{"stringValue": "e1"}]]},
    ]
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.side_effect = [
        _load_bedrock_fixture("classify_clean"),
        _load_bedrock_fixture("extract_clean"),
    ]

    with patch(
        "pipeline.silver.classify_extract_handler.boto3.client",
        side_effect=_boto_client_stub(rds_client, bedrock_client),
    ):
        result = handler(_event(), None)

    assert result["extraction_id"] == "e1"
    assert result["composite_confidence"] > 0.9

    insert_sql = rds_client.execute_statement.call_args_list[2].kwargs["sql"]
    assert "INSERT INTO extractions" in insert_sql
    insert_params = {
        p["name"]: p["value"]
        for p in rds_client.execute_statement.call_args_list[2].kwargs["parameters"]
    }
    fields = json.loads(insert_params["fields"]["stringValue"])
    assert set(fields) == set(EXPECTED_CLAIM_FIELDS)


def test_silver_handler_missing_fields_document_yields_lower_composite_than_clean():
    def _run(classify_fixture: str, extract_fixture: str) -> float:
        rds_client = _rds_client_for("c1", _line_blocks("SYNTHETIC MEDICAL CLAIM FORM"), 0.98)
        rds_client.execute_statement.side_effect = [
            rds_client.execute_statement.return_value,
            {},
            {"records": [[{"stringValue": "e1"}]]},
        ]
        bedrock_client = MagicMock()
        bedrock_client.invoke_model.side_effect = [
            _load_bedrock_fixture(classify_fixture),
            _load_bedrock_fixture(extract_fixture),
        ]
        with patch(
            "pipeline.silver.classify_extract_handler.boto3.client",
            side_effect=_boto_client_stub(rds_client, bedrock_client),
        ):
            return handler(_event(), None)["composite_confidence"]

    clean_score = _run("classify_clean", "extract_clean")
    missing_score = _run("classify_missing_fields", "extract_missing_fields")

    assert missing_score < clean_score


def test_silver_handler_non_claim_document_skips_extraction():
    rds_client = _rds_client_for("c1", _line_blocks("GROCERY RECEIPT"), 0.9)
    rds_client.execute_statement.side_effect = [
        rds_client.execute_statement.return_value,
        {},
        {"records": [[{"stringValue": "e1"}]]},
    ]
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.return_value = _mock_bedrock_response(
        _mock_tool_use_payload("classify_document", {"document_type": "other"})
    )

    with patch(
        "pipeline.silver.classify_extract_handler.boto3.client",
        side_effect=_boto_client_stub(rds_client, bedrock_client),
    ):
        result = handler(_event(), None)

    # Only the classify call happens — extraction is skipped for non-claim docs.
    assert bedrock_client.invoke_model.call_count == 1

    insert_params = {
        p["name"]: p["value"]
        for p in rds_client.execute_statement.call_args_list[2].kwargs["parameters"]
    }
    assert json.loads(insert_params["fields"]["stringValue"]) == {}
    assert insert_params["completeness_score"]["doubleValue"] == 0.0
    assert insert_params["extract_confidence"] == {"isNull": True}
    # extract weight coalesces to parse_confidence (0.9): 0.8*0.9 + 0.2*0.0
    assert result["composite_confidence"] == pytest.approx(0.8 * 0.9)


def test_silver_handler_bedrock_permanent_failure_marks_claim_failed_and_reraises():
    rds_client = _rds_client_for("c1", _line_blocks("SYNTHETIC MEDICAL CLAIM FORM"), 0.98)
    rds_client.execute_statement.side_effect = [
        rds_client.execute_statement.return_value,
        {},  # failed-status UPDATE
    ]
    bedrock_client = MagicMock()
    bedrock_client.invoke_model.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "retries exhausted"}}, "InvokeModel"
    )

    with (
        patch(
            "pipeline.silver.classify_extract_handler.boto3.client",
            side_effect=_boto_client_stub(rds_client, bedrock_client),
        ),
        pytest.raises(ClientError),
    ):
        handler(_event(), None)

    failed_update_sql = rds_client.execute_statement.call_args_list[1].kwargs["sql"]
    assert "SET status = 'failed'" in failed_update_sql
