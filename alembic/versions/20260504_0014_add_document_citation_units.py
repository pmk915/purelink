"""add document citation units

Revision ID: 20260504_0014
Revises: 20260429_0013
Create Date: 2026-05-04 11:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260504_0014"
down_revision = "20260429_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_citation_units",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("chunk_key", sa.String(length=255), nullable=False),
        sa.Column("unit_index", sa.Integer(), nullable=False),
        sa.Column("unit_text", sa.Text(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=True),
        sa.Column("end_char", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_citation_units")),
        sa.UniqueConstraint(
            "document_id",
            "unit_index",
            name="uq_document_citation_units_document_id_unit_index",
        ),
    )
    op.create_index(
        op.f("ix_document_citation_units_document_id"),
        "document_citation_units",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_citation_units_knowledge_base_id"),
        "document_citation_units",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_citation_units_chunk_key"),
        "document_citation_units",
        ["chunk_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_document_citation_units_chunk_key"),
        table_name="document_citation_units",
    )
    op.drop_index(
        op.f("ix_document_citation_units_knowledge_base_id"),
        table_name="document_citation_units",
    )
    op.drop_index(
        op.f("ix_document_citation_units_document_id"),
        table_name="document_citation_units",
    )
    op.drop_table("document_citation_units")
