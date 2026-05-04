"""fix document citation unit timestamp defaults

Revision ID: 20260504_0015
Revises: 20260504_0014
Create Date: 2026-05-04 18:35:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260504_0015"
down_revision = "20260504_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "document_citation_units",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        existing_nullable=False,
    )
    op.alter_column(
        "document_citation_units",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "document_citation_units",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "document_citation_units",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
