"""add chunk fk to document citation units

Revision ID: 20260504_0016
Revises: 20260504_0015
Create Date: 2026-05-04 22:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260504_0016"
down_revision = "20260504_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_citation_units",
        sa.Column("chunk_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_document_citation_units_chunk_id"),
        "document_citation_units",
        ["chunk_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE document_citation_units AS u
        SET chunk_id = c.id
        FROM document_chunks AS c
        WHERE u.document_id = c.document_id
          AND u.chunk_key = c.chunk_key
        """
    )
    op.execute(
        """
        DELETE FROM document_citation_units
        WHERE chunk_id IS NULL
        """
    )
    op.alter_column(
        "document_citation_units",
        "chunk_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_document_citation_units_chunk_id_document_chunks",
        "document_citation_units",
        "document_chunks",
        ["chunk_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_document_citation_units_chunk_id_unit_index",
        "document_citation_units",
        ["chunk_id", "unit_index"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_document_citation_units_chunk_id_unit_index",
        "document_citation_units",
        type_="unique",
    )
    op.drop_constraint(
        "fk_document_citation_units_chunk_id_document_chunks",
        "document_citation_units",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_document_citation_units_chunk_id"),
        table_name="document_citation_units",
    )
    op.drop_column("document_citation_units", "chunk_id")
