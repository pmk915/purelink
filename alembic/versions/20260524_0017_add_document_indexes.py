"""add document indexes

Revision ID: 20260524_0017
Revises: 20260504_0016
Create Date: 2026-05-24 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0017"
down_revision = "20260504_0016"
branch_labels = None
depends_on = None


document_index_type = sa.Enum(
    "vector",
    "graph",
    "lexical",
    name="document_index_type",
    native_enum=False,
    create_constraint=True,
)
document_index_status = sa.Enum(
    "pending",
    "indexing",
    "indexed",
    "stale",
    "failed",
    name="document_index_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "document_indexes",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("index_type", document_index_type, nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_dim", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(length=255), nullable=True),
        sa.Column("status", document_index_status, server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_indexes")),
        sa.UniqueConstraint(
            "document_id",
            "index_type",
            name="uq_document_indexes_document_id_index_type",
        ),
    )
    op.create_index(
        op.f("ix_document_indexes_document_id"),
        "document_indexes",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_indexes_knowledge_base_id"),
        "document_indexes",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_indexes_index_type"),
        "document_indexes",
        ["index_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_indexes_status"),
        "document_indexes",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_document_indexes_provider_model_name",
        "document_indexes",
        ["provider", "model_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_indexes_provider_model_name", table_name="document_indexes")
    op.drop_index(op.f("ix_document_indexes_status"), table_name="document_indexes")
    op.drop_index(op.f("ix_document_indexes_index_type"), table_name="document_indexes")
    op.drop_index(op.f("ix_document_indexes_knowledge_base_id"), table_name="document_indexes")
    op.drop_index(op.f("ix_document_indexes_document_id"), table_name="document_indexes")
    op.drop_table("document_indexes")
