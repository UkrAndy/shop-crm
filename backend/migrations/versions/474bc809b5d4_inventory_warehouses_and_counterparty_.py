"""inventory: warehouses and counterparty stubs

Revision ID: 474bc809b5d4
Revises: 4f2df2d0324b
Create Date: 2026-08-30 20:47:35.581892

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "474bc809b5d4"
down_revision: str | Sequence[str] | None = "4f2df2d0324b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "counterparties_stub",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_counterparties_name_not_blank"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_counterparties_organization_name"),
    )
    op.create_index(
        op.f("ix_counterparties_stub_organization_id"),
        "counterparties_stub",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_warehouses_name_not_blank"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # One warehouse per organization: the PRD scopes exactly one and puts
        # transfers out of scope. Lifting this must be a deliberate migration.
        sa.UniqueConstraint("organization_id", name="uq_warehouses_organization"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("warehouses")
    op.drop_index(op.f("ix_counterparties_stub_organization_id"), table_name="counterparties_stub")
    op.drop_table("counterparties_stub")
