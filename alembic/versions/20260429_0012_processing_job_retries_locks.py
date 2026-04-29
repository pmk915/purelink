"""add processing job retry and lock fields

Revision ID: 20260429_0012
Revises: 20260429_0011
Create Date: 2026-04-29 16:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0012"
down_revision = "20260429_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("locked_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_jobs_processing_job_status"),
    )
    op.execute(
        sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS processing_job_status"),
    )
    op.execute(
        sa.text("UPDATE processing_jobs SET status = 'processing' WHERE status = 'running'"),
    )
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_status "
            "CHECK (status IN ('queued', 'processing', 'retrying', 'succeeded', 'failed', 'cancelled'))",
        ),
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_jobs_processing_job_status"),
    )
    op.execute(
        sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS processing_job_status"),
    )
    op.execute(
        sa.text("UPDATE processing_jobs SET status = 'running' WHERE status = 'processing'"),
    )
    op.execute(
        sa.text("UPDATE processing_jobs SET status = 'queued' WHERE status = 'retrying'"),
    )
    op.execute(
        sa.text("UPDATE processing_jobs SET status = 'failed' WHERE status = 'cancelled'"),
    )
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_status "
            "CHECK (status IN ('queued', 'running', 'succeeded', 'failed'))",
        ),
    )
    op.drop_column("processing_jobs", "timeout_at")
    op.drop_column("processing_jobs", "locked_at")
    op.drop_column("processing_jobs", "locked_by")
    op.drop_column("processing_jobs", "max_retries")
    op.drop_column("processing_jobs", "retry_count")
