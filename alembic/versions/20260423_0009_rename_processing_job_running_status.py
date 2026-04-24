"""rename processing job processing status to running

Revision ID: 20260423_0009
Revises: 20260423_0008
Create Date: 2026-04-23 18:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0009"
down_revision = "20260423_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs DROP CONSTRAINT ck_processing_jobs_processing_job_status",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE processing_jobs SET status = 'running' WHERE status = 'processing'",
        ),
    )
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_status "
            "CHECK (status IN ('queued', 'running', 'succeeded', 'failed'))",
        ),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs DROP CONSTRAINT ck_processing_jobs_processing_job_status",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE processing_jobs SET status = 'processing' WHERE status = 'running'",
        ),
    )
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_status "
            "CHECK (status IN ('queued', 'processing', 'succeeded', 'failed'))",
        ),
    )
