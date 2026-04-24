"""add index processing jobs

Revision ID: 20260423_0010
Revises: 20260423_0009
Create Date: 2026-04-23 22:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_0010"
down_revision = "20260423_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_jobs_processing_job_type"))
    op.execute(sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS processing_job_type"))
    op.execute(sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_jobs_processing_job_trigger"))
    op.execute(sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS processing_job_trigger"))
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_type "
            "CHECK (job_type IN ('document_process', 'document_index'))",
        ),
    )
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_trigger "
            "CHECK (trigger_type IN ('process', 'retry', 'reprocess', 'index'))",
        ),
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_jobs_processing_job_type"))
    op.execute(sa.text("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS ck_processing_jobs_processing_job_trigger"))
    op.execute(
        sa.text(
            "UPDATE processing_jobs "
            "SET job_type = 'document_process' "
            "WHERE job_type = 'document_index'",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE processing_jobs "
            "SET trigger_type = 'reprocess' "
            "WHERE trigger_type = 'index'",
        ),
    )
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_type "
            "CHECK (job_type IN ('document_process'))",
        ),
    )
    op.execute(
        sa.text(
            "ALTER TABLE processing_jobs "
            "ADD CONSTRAINT ck_processing_jobs_processing_job_trigger "
            "CHECK (trigger_type IN ('process', 'retry', 'reprocess'))",
        ),
    )
