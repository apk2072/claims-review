"""Integration test: insert + read one row per table against the real dev
Aurora cluster (via the RDS Data API dialect — the cluster has no public
endpoint, so this is the same connection method Alembic uses).

Skipped automatically when AURORA_CLUSTER_ARN isn't set (e.g. plain `pytest`
runs without AWS context) — this is deliberately a real-infra integration
test per testing-standards.md, not a mocked unit test.
"""

import datetime
import os

import pytest
import sqlalchemy_aurora_data_api  # noqa: F401  (registers the dialect)
from common.models import AgentMemory, Claim, Extraction, Review, ReviewMetric
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

requires_aurora = pytest.mark.skipif(
    "AURORA_CLUSTER_ARN" not in os.environ,
    reason="AURORA_CLUSTER_ARN not set — skipping real-Aurora integration test",
)


@pytest.fixture
def db_session():
    db_name = os.environ.get("AURORA_DATABASE_NAME", "claims_review")
    engine = create_engine(f"postgresql+auroradataapi://:@/{db_name}")
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.rollback()  # never persist test data in the dev cluster
        session.close()


@requires_aurora
def test_insert_and_read_one_row_per_table(db_session: Session):
    claim = Claim(s3_key="test/schema-check.png", document_type="claim_form", status="pending")
    db_session.add(claim)
    db_session.flush()
    assert claim.id is not None

    extraction = Extraction(
        claim_id=claim.id,
        fields={"patient_name": "Jane Test Doe"},
        field_confidences={"patient_name": 0.97},
        parse_confidence=0.95,
        extract_confidence=0.97,
        completeness_score=1.0,
        composite_confidence=0.96,
        is_automated=True,
    )
    db_session.add(extraction)
    db_session.flush()
    assert extraction.id is not None

    review = Review(
        extraction_id=extraction.id,
        reviewer_email="reviewer@test.example",
        verdict="approved",
    )
    db_session.add(review)
    db_session.flush()
    assert review.id is not None

    metric = ReviewMetric(
        reviewer_email="reviewer@test.example",
        metric_date=datetime.datetime.now(datetime.UTC),
        approved_count=1,
    )
    db_session.add(metric)
    db_session.flush()
    assert metric.id is not None

    memory = AgentMemory(
        user_email="reviewer@test.example",
        content="schema smoke test memory row",
        embedding=[0.0] * 1024,
    )
    db_session.add(memory)
    db_session.flush()
    assert memory.id is not None

    # Read back within the same (uncommitted) transaction.
    fetched_claim = db_session.get(Claim, claim.id)
    assert fetched_claim is not None
    assert fetched_claim.s3_key == "test/schema-check.png"

    fetched_extraction = db_session.get(Extraction, extraction.id)
    assert fetched_extraction is not None
    assert fetched_extraction.claim_id == claim.id

    fetched_review = db_session.get(Review, review.id)
    assert fetched_review is not None
    assert fetched_review.verdict == "approved"

    fetched_metric = db_session.get(ReviewMetric, metric.id)
    assert fetched_metric is not None
    assert fetched_metric.approved_count == 1

    fetched_memory = db_session.get(AgentMemory, memory.id)
    assert fetched_memory is not None
    assert fetched_memory.content == "schema smoke test memory row"
