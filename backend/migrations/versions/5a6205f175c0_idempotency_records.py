"""idempotency records

Revision ID: 5a6205f175c0
Revises: 5951163f2067
Create Date: 2026-08-30 21:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5a6205f175c0"
down_revision: str | Sequence[str] | None = "5951163f2067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        # SHA-256 over a canonical rendering of the request: this is how a replay
        # is told apart from the same key reused for different work.
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Not a nicety — the mechanism. Two concurrent requests carrying the same
        # key both attempt this insert; PostgreSQL makes the second wait on the
        # index, and whichever loses reads the winner's stored response instead
        # of executing. Scoped per organization because client-supplied keys are
        # not globally unique, and per endpoint because one key reaching two
        # different commands is two different pieces of work.
        sa.UniqueConstraint(
            "organization_id", "endpoint", "key", name="uq_idempotency_records_scope"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("idempotency_records")
