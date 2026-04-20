"""expand document task types

Revision ID: 20260421_0005
Revises: 20260421_0004
Create Date: 2026-04-21 13:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260421_0005"
down_revision = "20260421_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("document_tasks") as batch_op:
        batch_op.drop_constraint("document_task_type", type_="check")
        batch_op.create_check_constraint(
            "document_task_type",
            "task_type IN ('parse', 'chunk', 'embed', 'index')",
        )


def downgrade() -> None:
    with op.batch_alter_table("document_tasks") as batch_op:
        batch_op.drop_constraint("document_task_type", type_="check")
        batch_op.create_check_constraint(
            "document_task_type",
            "task_type IN ('parse')",
        )
