"""add retrieval traces

Revision ID: 20260525_0018
Revises: 20260524_0017
Create Date: 2026-05-25 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_0018"
down_revision = "20260524_0017"
branch_labels = None
depends_on = None


retrieval_filtered_reason = sa.Enum(
    "not_filtered",
    "not_selected_after_rerank",
    "low_score",
    "incompatible_index",
    "stale_index",
    "legacy_unknown_allowed",
    "missing_index",
    "document_not_ready",
    "permission_filtered",
    "unknown",
    name="retrieval_filtered_reason",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "retrieval_traces",
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=True),
        sa.Column("initial_candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("final_evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reranker_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("used_reranker", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reranker_provider", sa.String(length=100), nullable=True),
        sa.Column("reranker_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_provider", sa.String(length=100), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_traces")),
    )
    op.create_index(op.f("ix_retrieval_traces_user_id"), "retrieval_traces", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_retrieval_traces_knowledge_base_id"),
        "retrieval_traces",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_traces_conversation_id"),
        "retrieval_traces",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(op.f("ix_retrieval_traces_message_id"), "retrieval_traces", ["message_id"], unique=False)
    op.create_index(op.f("ix_retrieval_traces_created_at"), "retrieval_traces", ["created_at"], unique=False)
    op.create_index(op.f("ix_retrieval_traces_mode"), "retrieval_traces", ["mode"], unique=False)

    op.create_table(
        "retrieval_trace_items",
        sa.Column("trace_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("citation_unit_id", sa.Integer(), nullable=True),
        sa.Column("document_name", sa.String(length=255), nullable=True),
        sa.Column("source_locator", sa.String(length=255), nullable=True),
        sa.Column("candidate_text_preview", sa.Text(), nullable=True),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("keyword_score", sa.Float(), nullable=True),
        sa.Column("graph_score", sa.Float(), nullable=True),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("initial_rank", sa.Integer(), nullable=True),
        sa.Column("rerank_rank", sa.Integer(), nullable=True),
        sa.Column("final_rank", sa.Integer(), nullable=True),
        sa.Column("selected_for_context", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("filtered_reason", retrieval_filtered_reason, server_default="unknown", nullable=False),
        sa.Column("index_status", sa.String(length=50), nullable=True),
        sa.Column("index_provider", sa.String(length=100), nullable=True),
        sa.Column("index_model_name", sa.String(length=255), nullable=True),
        sa.Column("index_model_dim", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["citation_unit_id"], ["document_citation_units.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trace_id"], ["retrieval_traces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_trace_items")),
    )
    op.create_index(op.f("ix_retrieval_trace_items_trace_id"), "retrieval_trace_items", ["trace_id"], unique=False)
    op.create_index(
        op.f("ix_retrieval_trace_items_document_id"),
        "retrieval_trace_items",
        ["document_id"],
        unique=False,
    )
    op.create_index(op.f("ix_retrieval_trace_items_chunk_id"), "retrieval_trace_items", ["chunk_id"], unique=False)
    op.create_index(
        op.f("ix_retrieval_trace_items_citation_unit_id"),
        "retrieval_trace_items",
        ["citation_unit_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_trace_items_selected_for_context"),
        "retrieval_trace_items",
        ["selected_for_context"],
        unique=False,
    )
    op.create_index(
        op.f("ix_retrieval_trace_items_filtered_reason"),
        "retrieval_trace_items",
        ["filtered_reason"],
        unique=False,
    )
    op.create_index(
        "ix_retrieval_trace_items_trace_final_rank",
        "retrieval_trace_items",
        ["trace_id", "final_rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_trace_items_trace_final_rank", table_name="retrieval_trace_items")
    op.drop_index(op.f("ix_retrieval_trace_items_filtered_reason"), table_name="retrieval_trace_items")
    op.drop_index(op.f("ix_retrieval_trace_items_selected_for_context"), table_name="retrieval_trace_items")
    op.drop_index(op.f("ix_retrieval_trace_items_citation_unit_id"), table_name="retrieval_trace_items")
    op.drop_index(op.f("ix_retrieval_trace_items_chunk_id"), table_name="retrieval_trace_items")
    op.drop_index(op.f("ix_retrieval_trace_items_document_id"), table_name="retrieval_trace_items")
    op.drop_index(op.f("ix_retrieval_trace_items_trace_id"), table_name="retrieval_trace_items")
    op.drop_table("retrieval_trace_items")
    op.drop_index(op.f("ix_retrieval_traces_mode"), table_name="retrieval_traces")
    op.drop_index(op.f("ix_retrieval_traces_created_at"), table_name="retrieval_traces")
    op.drop_index(op.f("ix_retrieval_traces_message_id"), table_name="retrieval_traces")
    op.drop_index(op.f("ix_retrieval_traces_conversation_id"), table_name="retrieval_traces")
    op.drop_index(op.f("ix_retrieval_traces_knowledge_base_id"), table_name="retrieval_traces")
    op.drop_index(op.f("ix_retrieval_traces_user_id"), table_name="retrieval_traces")
    op.drop_table("retrieval_traces")
