"""add txt processing metadata and document chunks

Revision ID: 20260422_0006
Revises: 20260421_0005
Create Date: 2026-04-22 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260422_0006"
down_revision = "20260421_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.drop_constraint("document_processing_status", type_="check")
        batch_op.create_check_constraint(
            "document_processing_status",
            "processing_status IN ('uploaded', 'processing', 'parsed', 'indexed', 'ready', 'failed')",
        )

    op.create_table(
        "document_chunks",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_key", sa.String(length=255), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint("chunk_key", name="uq_document_chunks_chunk_key"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_id_chunk_index",
        ),
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"),
        "document_chunks",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")

    op.execute(
        """
        UPDATE documents
        SET processing_status = CASE processing_status
            WHEN 'processing' THEN 'uploaded'
            WHEN 'ready' THEN 'indexed'
            ELSE processing_status
        END
        """
    )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("document_processing_status", type_="check")
        batch_op.create_check_constraint(
            "document_processing_status",
            "processing_status IN ('uploaded', 'parsed', 'indexed', 'failed')",
        )
        batch_op.drop_column("processed_at")
        batch_op.drop_column("error_message")
