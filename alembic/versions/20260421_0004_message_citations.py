"""add citations storage to messages

Revision ID: 20260421_0004
Revises: 20260420_0003
Create Date: 2026-04-21 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_0004"
down_revision = "20260420_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("citations_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "citations_json")
