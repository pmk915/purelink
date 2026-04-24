"""add processing jobs table for engineered document processing

Revision ID: 20260423_0007
Revises: 20260422_0006
Create Date: 2026-04-23 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0007"
down_revision = "20260422_0006"
branch_labels = None
depends_on = None


processing_job_type = sa.Enum(
    "document_process",
    name="processing_job_type",
    native_enum=False,
    create_constraint=True,
)

processing_job_trigger = sa.Enum(
    "process",
    "retry",
    "reprocess",
    name="processing_job_trigger",
    native_enum=False,
    create_constraint=True,
)

processing_job_status = sa.Enum(
    "queued",
    "processing",
    "succeeded",
    "failed",
    name="processing_job_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("triggered_by_id", sa.Integer(), nullable=False),
        sa.Column("previous_job_id", sa.Integer(), nullable=True),
        sa.Column("job_type", processing_job_type, nullable=False, server_default="document_process"),
        sa.Column("trigger_type", processing_job_trigger, nullable=False, server_default="process"),
        sa.Column("status", processing_job_status, nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("worker_name", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_processing_jobs_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_job_id"],
            ["processing_jobs.id"],
            name=op.f("fk_processing_jobs_previous_job_id_processing_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_id"],
            ["users.id"],
            name=op.f("fk_processing_jobs_triggered_by_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_jobs")),
    )
    op.create_index(op.f("ix_processing_jobs_document_id"), "processing_jobs", ["document_id"], unique=False)
    op.create_index(
        op.f("ix_processing_jobs_previous_job_id"),
        "processing_jobs",
        ["previous_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_processing_jobs_triggered_by_id"),
        "processing_jobs",
        ["triggered_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_jobs_triggered_by_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_previous_job_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_document_id"), table_name="processing_jobs")
    op.drop_table("processing_jobs")
