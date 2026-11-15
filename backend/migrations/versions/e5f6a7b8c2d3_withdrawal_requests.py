"""farmer withdrawal requests

Revision ID: e5f6a7b8c2d3
Revises: d4e5f6a7b8c1
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c2d3"
down_revision = "d4e5f6a7b8c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "withdrawal_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("farmer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=4), nullable=False, server_default="INR"),
        sa.Column("method", sa.String(length=8), nullable=True),
        sa.Column("account_masked", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="requested", index=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.String(length=40), nullable=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("payout_batches.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("withdrawal_requests")
