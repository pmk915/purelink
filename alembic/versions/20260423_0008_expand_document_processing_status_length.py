"""expand document processing_status column length for new states

Revision ID: 20260423_0008
Revises: 20260423_0007
Create Date: 2026-04-23 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0008"
down_revision = "20260423_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column(
            "processing_status",
            existing_type=sa.String(length=8),
            type_=sa.String(length=16),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column(
            "processing_status",
            existing_type=sa.String(length=16),
            type_=sa.String(length=8),
            existing_nullable=False,
        )
