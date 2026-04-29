"""add processing job error code

Revision ID: 20260429_0011
Revises: 20260423_0010
Create Date: 2026-04-29 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0011"
down_revision = "20260423_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs",
        sa.Column("error_code", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("processing_jobs", "error_code")
