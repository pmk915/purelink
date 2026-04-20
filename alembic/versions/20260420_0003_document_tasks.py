"""Add document task table for background processing

Revision ID: 20260420_0003
Revises: 20260420_0002
Create Date: 2026-04-20 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_0003"
down_revision = "20260420_0002"
branch_labels = None
depends_on = None


document_task_type = sa.Enum(
    "parse",
    name="document_task_type",
    native_enum=False,
    create_constraint=True,
)

document_task_status = sa.Enum(
    "pending",
    "processing",
    "succeeded",
    "failed",
    name="document_task_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "document_tasks",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("task_type", document_task_type, nullable=False),
        sa.Column("status", document_task_status, nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_tasks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_tasks")),
    )
    op.create_index(op.f("ix_document_tasks_document_id"), "document_tasks", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_document_tasks_document_id"), table_name="document_tasks")
    op.drop_table("document_tasks")
