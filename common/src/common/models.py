"""SQLAlchemy models for the claims-review operational schema.

Shared by pipeline (writes claims/extractions), backend (reads/writes
reviews + review_metrics), and agent (reads/writes agent_memory).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector as _PgVector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, cast, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Matches Amazon Titan Embed Text v2's default output dimension. Revisit if
# the agent work item picks a different Bedrock embedding model.
AGENT_MEMORY_EMBEDDING_DIM = 1024


class Vector(_PgVector):
    """pgvector's Vector type, with an explicit ::vector cast on bind.

    Needed because the RDS Data API (used by Alembic migrations — Aurora has
    no public endpoint) sends bind parameters without Postgres type-OID
    negotiation, so an un-cast vector parameter arrives as plain text and
    Postgres rejects the implicit text->vector conversion. A normal psycopg
    connection (backend/agent, once they're built) negotiates the type over
    the wire protocol and wouldn't need this — but the explicit cast is a
    no-op for it, so this subclass is safe to use everywhere.
    """

    def bind_expression(self, bindvalue):
        return cast(bindvalue, self)


# claims.status values (kept as a plain string column, not a Postgres ENUM,
# so adding a new status later doesn't require an ALTER TYPE migration).
CLAIM_STATUSES = ("processing", "pending", "auto_verified", "human_review", "reviewed", "failed")

# reviews.verdict values
REVIEW_VERDICTS = ("approved", "rejected", "corrected")


class Base(DeclarativeBase):
    pass


class Claim(Base):
    """One row per ingested claim document (bronze-layer identity)."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    s3_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    document_type: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Extraction(Base):
    """Gold-layer extraction result: fields, confidence scores, auto-verdict routing."""

    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False
    )
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    field_confidences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parse_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extract_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_automated: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    """One row per reviewer verdict action. Insert-only — this table IS the audit trail."""

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extractions.id"), nullable=False
    )
    reviewer_email: Mapped[str] = mapped_column(String, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    corrected_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewMetric(Base):
    """Per-reviewer, per-day aggregate — incremented alongside each Review insert."""

    __tablename__ = "review_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    reviewer_email: Mapped[str] = mapped_column(String, nullable=False)
    metric_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    corrected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentMemory(Base):
    """Long-term, per-user agent memory with pgvector similarity search."""

    __tablename__ = "agent_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_email: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(AGENT_MEMORY_EMBEDDING_DIM), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
