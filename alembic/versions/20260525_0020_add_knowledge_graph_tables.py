"""add knowledge graph tables

Revision ID: 20260525_0020
Revises: 20260525_0019
Create Date: 2026-05-25 02:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_0020"
down_revision = "20260525_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entities",
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases_json", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_entities")),
        sa.UniqueConstraint(
            "knowledge_base_id",
            "normalized_name",
            name="uq_knowledge_entities_knowledge_base_id_normalized_name",
        ),
    )
    op.create_index(op.f("ix_knowledge_entities_knowledge_base_id"), "knowledge_entities", ["knowledge_base_id"], unique=False)
    op.create_index(op.f("ix_knowledge_entities_normalized_name"), "knowledge_entities", ["normalized_name"], unique=False)
    op.create_index(op.f("ix_knowledge_entities_entity_type"), "knowledge_entities", ["entity_type"], unique=False)
    op.create_index("ix_knowledge_entities_kb_type", "knowledge_entities", ["knowledge_base_id", "entity_type"], unique=False)

    op.create_table(
        "knowledge_relations",
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("source_entity_id", sa.Integer(), nullable=False),
        sa.Column("target_entity_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("source_chunk_id", sa.Integer(), nullable=True),
        sa.Column("source_citation_unit_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_citation_unit_id"], ["document_citation_units.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_relations")),
    )
    op.create_index(op.f("ix_knowledge_relations_knowledge_base_id"), "knowledge_relations", ["knowledge_base_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_source_entity_id"), "knowledge_relations", ["source_entity_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_target_entity_id"), "knowledge_relations", ["target_entity_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_relation_type"), "knowledge_relations", ["relation_type"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_source_document_id"), "knowledge_relations", ["source_document_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_source_chunk_id"), "knowledge_relations", ["source_chunk_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_source_citation_unit_id"), "knowledge_relations", ["source_citation_unit_id"], unique=False)
    op.create_index("ix_knowledge_relations_kb_relation_type", "knowledge_relations", ["knowledge_base_id", "relation_type"], unique=False)
    op.create_index("ix_knowledge_relations_source_target", "knowledge_relations", ["source_entity_id", "target_entity_id"], unique=False)

    op.create_table(
        "entity_mentions",
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("citation_unit_id", sa.Integer(), nullable=True),
        sa.Column("text_span", sa.String(length=255), nullable=True),
        sa.Column("source_locator", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["citation_unit_id"], ["document_citation_units.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity_mentions")),
    )
    op.create_index(op.f("ix_entity_mentions_entity_id"), "entity_mentions", ["entity_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_knowledge_base_id"), "entity_mentions", ["knowledge_base_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_document_id"), "entity_mentions", ["document_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_chunk_id"), "entity_mentions", ["chunk_id"], unique=False)
    op.create_index(op.f("ix_entity_mentions_citation_unit_id"), "entity_mentions", ["citation_unit_id"], unique=False)
    op.create_index("ix_entity_mentions_entity_document", "entity_mentions", ["entity_id", "document_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_entity_mentions_entity_document", table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_citation_unit_id"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_chunk_id"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_document_id"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_knowledge_base_id"), table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_entity_id"), table_name="entity_mentions")
    op.drop_table("entity_mentions")

    op.drop_index("ix_knowledge_relations_source_target", table_name="knowledge_relations")
    op.drop_index("ix_knowledge_relations_kb_relation_type", table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_source_citation_unit_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_source_chunk_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_source_document_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_relation_type"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_target_entity_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_source_entity_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_knowledge_base_id"), table_name="knowledge_relations")
    op.drop_table("knowledge_relations")

    op.drop_index("ix_knowledge_entities_kb_type", table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_entity_type"), table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_normalized_name"), table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_knowledge_base_id"), table_name="knowledge_entities")
    op.drop_table("knowledge_entities")
