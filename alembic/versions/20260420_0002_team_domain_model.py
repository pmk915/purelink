"""Add team domain model and multi-scope knowledge bases

Revision ID: 20260420_0002
Revises: 20260411_0001
Create Date: 2026-04-20 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_0002"
down_revision = "20260411_0001"
branch_labels = None
depends_on = None


knowledge_base_scope = sa.Enum(
    "personal",
    "team",
    name="knowledge_base_scope",
    native_enum=False,
    create_constraint=True,
)

document_review_status = sa.Enum(
    "not_required",
    "pending_review",
    "approved",
    "rejected",
    name="document_review_status",
    native_enum=False,
    create_constraint=True,
)

document_processing_status = sa.Enum(
    "uploaded",
    "parsed",
    "indexed",
    "failed",
    name="document_processing_status",
    native_enum=False,
    create_constraint=True,
)

team_member_role = sa.Enum(
    "admin",
    "member",
    name="team_member_role",
    native_enum=False,
    create_constraint=True,
)

team_member_status = sa.Enum(
    "active",
    "invited",
    "removed",
    name="team_member_status",
    native_enum=False,
    create_constraint=True,
)

team_invite_status = sa.Enum(
    "active",
    "used",
    "expired",
    "revoked",
    name="team_invite_status",
    native_enum=False,
    create_constraint=True,
)

legacy_document_status = sa.Enum(
    "uploaded",
    "processing",
    "indexed",
    "failed",
    name="document_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_teams_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    op.create_index(op.f("ix_teams_created_by"), "teams", ["created_by"], unique=False)

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", team_member_role, nullable=False),
        sa.Column("status", team_member_status, nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_members_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_team_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_members")),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_id_user_id"),
    )
    op.create_index(op.f("ix_team_members_team_id"), "team_members", ["team_id"], unique=False)
    op.create_index(op.f("ix_team_members_user_id"), "team_members", ["user_id"], unique=False)

    op.create_table(
        "team_invites",
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("invited_by", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_by", sa.Integer(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", team_invite_status, nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_invites_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_team_invites_invited_by_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["used_by"],
            ["users.id"],
            name=op.f("fk_team_invites_used_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_invites")),
    )
    op.create_index(op.f("ix_team_invites_code"), "team_invites", ["code"], unique=True)
    op.create_index(op.f("ix_team_invites_invited_by"), "team_invites", ["invited_by"], unique=False)
    op.create_index(op.f("ix_team_invites_team_id"), "team_invites", ["team_id"], unique=False)
    op.create_index(op.f("ix_team_invites_used_by"), "team_invites", ["used_by"], unique=False)

    with op.batch_alter_table("knowledge_bases") as batch_op:
        batch_op.add_column(
            sa.Column(
                "scope",
                knowledge_base_scope,
                server_default="personal",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("team_id", sa.Integer(), nullable=True))
        batch_op.alter_column(
            "owner_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.create_foreign_key(
            op.f("fk_knowledge_bases_team_id_teams"),
            "teams",
            ["team_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(op.f("ix_knowledge_bases_team_id"), ["team_id"], unique=False)
        batch_op.create_check_constraint(
            op.f("ck_knowledge_bases_scope_owner_team_consistency"),
            "("
            "(scope = 'personal' AND owner_id IS NOT NULL AND team_id IS NULL) "
            "OR "
            "(scope = 'team' AND owner_id IS NULL AND team_id IS NOT NULL)"
            ")",
        )

    op.execute("UPDATE knowledge_bases SET scope = 'personal' WHERE scope IS NULL")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("submitted_by", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "review_status",
                document_review_status,
                server_default="not_required",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("processing_status", document_processing_status, nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("review_comment", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_documents_submitted_by_users"),
            "users",
            ["submitted_by"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            op.f("fk_documents_reviewed_by_users"),
            "users",
            ["reviewed_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_documents_submitted_by"), ["submitted_by"], unique=False)
        batch_op.create_index(op.f("ix_documents_reviewed_by"), ["reviewed_by"], unique=False)

    op.execute(
        """
        UPDATE documents
        SET
            submitted_by = owner_id,
            review_status = 'not_required',
            processing_status = CASE status
                WHEN 'uploaded' THEN 'uploaded'
                WHEN 'processing' THEN 'parsed'
                WHEN 'indexed' THEN 'indexed'
                WHEN 'failed' THEN 'failed'
                ELSE 'uploaded'
            END
        """
    )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint(op.f("ck_documents_document_status"), type_="check")
        batch_op.alter_column(
            "submitted_by",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "processing_status",
            existing_type=document_processing_status,
            server_default="uploaded",
            nullable=False,
        )
        batch_op.drop_column("status")


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                legacy_document_status,
                nullable=True,
            )
        )

    op.execute(
        """
        UPDATE documents
        SET status = CASE processing_status
            WHEN 'uploaded' THEN 'uploaded'
            WHEN 'parsed' THEN 'processing'
            WHEN 'indexed' THEN 'indexed'
            WHEN 'failed' THEN 'failed'
            ELSE 'uploaded'
        END
        """
    )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=legacy_document_status,
            server_default="uploaded",
            nullable=False,
        )
        batch_op.drop_constraint("document_processing_status", type_="check")
        batch_op.drop_constraint("document_review_status", type_="check")
        batch_op.drop_index(op.f("ix_documents_reviewed_by"))
        batch_op.drop_index(op.f("ix_documents_submitted_by"))
        batch_op.drop_constraint(op.f("fk_documents_reviewed_by_users"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_documents_submitted_by_users"), type_="foreignkey")
        batch_op.drop_column("review_comment")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("processing_status")
        batch_op.drop_column("review_status")
        batch_op.drop_column("submitted_by")

    op.execute(
        """
        UPDATE conversations
        SET knowledge_base_id = NULL
        WHERE knowledge_base_id IN (
            SELECT id FROM knowledge_bases WHERE scope = 'team'
        )
        """
    )
    op.execute(
        """
        DELETE FROM documents
        WHERE knowledge_base_id IN (
            SELECT id FROM knowledge_bases WHERE scope = 'team'
        )
        """
    )
    op.execute("DELETE FROM knowledge_bases WHERE scope = 'team'")

    with op.batch_alter_table("knowledge_bases") as batch_op:
        batch_op.drop_constraint(op.f("ck_knowledge_bases_scope_owner_team_consistency"), type_="check")
        batch_op.drop_index(op.f("ix_knowledge_bases_team_id"))
        batch_op.drop_constraint(op.f("fk_knowledge_bases_team_id_teams"), type_="foreignkey")
        batch_op.drop_column("team_id")
        batch_op.drop_column("scope")
        batch_op.alter_column(
            "owner_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    op.drop_index(op.f("ix_team_invites_used_by"), table_name="team_invites")
    op.drop_index(op.f("ix_team_invites_team_id"), table_name="team_invites")
    op.drop_index(op.f("ix_team_invites_invited_by"), table_name="team_invites")
    op.drop_index(op.f("ix_team_invites_code"), table_name="team_invites")
    op.drop_table("team_invites")

    op.drop_index(op.f("ix_team_members_user_id"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_team_id"), table_name="team_members")
    op.drop_table("team_members")

    op.drop_index(op.f("ix_teams_created_by"), table_name="teams")
    op.drop_table("teams")
