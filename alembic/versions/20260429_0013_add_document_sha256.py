"""add document sha256 for upload dedupe

Revision ID: 20260429_0013
Revises: 20260429_0012
Create Date: 2026-04-29 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0013"
down_revision = "20260429_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sha256", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_documents_knowledge_base_sha256",
        "documents",
        ["knowledge_base_id", "sha256"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_knowledge_base_sha256",
        "documents",
        type_="unique",
    )
    op.drop_column("documents", "sha256")
