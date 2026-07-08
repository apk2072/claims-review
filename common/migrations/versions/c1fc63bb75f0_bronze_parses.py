"""bronze parses

Revision ID: c1fc63bb75f0
Revises: e3cd55308ea0
Create Date: 2026-07-07 19:31:27.176917

Hand-written, same reason as the initial migration: autogenerate's
reflection query is incompatible with the RDS Data API.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1fc63bb75f0"
down_revision: str | Sequence[str] | None = "e3cd55308ea0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "bronze_parses",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "claim_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("raw_blocks", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("parse_confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("bronze_parses")
