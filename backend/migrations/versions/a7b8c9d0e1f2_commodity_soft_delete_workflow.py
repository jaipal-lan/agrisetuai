"""commodity soft-delete + removal request/approve workflow

Adds an `active` flag and deletion-request fields to commodities so field
leaders/managers can request removal and the superadmin approves it.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("commodities") as batch:
        batch.add_column(sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("deletion_requested_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("deletion_requested_at", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("deletion_reason", sa.String(length=300), nullable=True))
        batch.create_index("ix_commodities_active", ["active"])


def downgrade() -> None:
    with op.batch_alter_table("commodities") as batch:
        batch.drop_index("ix_commodities_active")
        batch.drop_column("deletion_reason")
        batch.drop_column("deletion_requested_at")
        batch.drop_column("deletion_requested_by")
        batch.drop_column("active")
