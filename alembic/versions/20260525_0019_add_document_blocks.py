"""add document blocks

Revision ID: 20260525_0019
Revises: 20260525_0018
Create Date: 2026-05-25 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_0019"
down_revision = "20260525_0018"
branch_labels = None
depends_on = None


document_block_type = sa.Enum(
    "text",
    "heading",
    "table",
    "code",
    "image",
    "formula",
    "unknown",
    name="document_block_type",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "document_blocks",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("block_type", document_block_type, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_locator", sa.String(length=255), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("heading_level", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_blocks")),
        sa.UniqueConstraint(
            "document_id",
            "order_index",
            name="uq_document_blocks_document_id_order_index",
        ),
    )
    op.create_index(op.f("ix_document_blocks_document_id"), "document_blocks", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_blocks_block_type"), "document_blocks", ["block_type"], unique=False)
    op.create_index(op.f("ix_document_blocks_order_index"), "document_blocks", ["order_index"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_document_blocks_order_index"), table_name="document_blocks")
    op.drop_index(op.f("ix_document_blocks_block_type"), table_name="document_blocks")
    op.drop_index(op.f("ix_document_blocks_document_id"), table_name="document_blocks")
    op.drop_table("document_blocks")
