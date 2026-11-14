"""RFQ price range, source areas, escalation + comment thread

Adds price band, multi-area sourcing and agent-escalation fields to RFQs, plus a
shared comment/activity thread (rfq_comments).

Revision ID: b2c3d4e5f6a8
Revises: a7b8c9d0e1f2
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a8"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rfqs") as batch:
        batch.add_column(sa.Column("price_min", sa.Numeric(precision=12, scale=2), nullable=True))
        batch.add_column(sa.Column("price_max", sa.Numeric(precision=12, scale=2), nullable=True))
        batch.add_column(sa.Column("source_mandal_ids", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("escalated_at", sa.String(length=40), nullable=True))
        batch.create_index("ix_rfqs_escalated", ["escalated"])

    op.create_table(
        "rfq_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id"), nullable=False, index=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("rfq_comments")
    with op.batch_alter_table("rfqs") as batch:
        batch.drop_index("ix_rfqs_escalated")
        batch.drop_column("escalated_at")
        batch.drop_column("escalated")
        batch.drop_column("source_mandal_ids")
        batch.drop_column("price_max")
        batch.drop_column("price_min")
